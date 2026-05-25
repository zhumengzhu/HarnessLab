"""Localhost HTTP server + JSON API for the chat Web UI."""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from harnesslab.core.loop import DEFAULT_MAX_STEPS, HarnessLoop
from harnesslab.core.memory_policy import session_memory_key
from harnesslab.core.models import Session, TraceEvent
from harnesslab.replay.trace_reader import read_trace
from harnesslab.telemetry.log import get_logger
from harnesslab.web.trace_hub import TraceHub

_LEGACY_STATIC_DIR = Path(__file__).resolve().parent / "static"
_TS_STATIC_DIR = Path(__file__).resolve().parent / "static_ts"
_log = get_logger("web.server")
_GATE_TIMEOUT_SECONDS = 600
_GATE_OUTPUT_LIMIT = 12000

TOOL_PANEL_EVENT_TYPES = frozenset(
    {
        "step_started",
        "step_completed",
        "decision_made",
        "tool_executed",
        "tool_denied",
        "tool_invalid_args",
        "memory_read",
        "memory_written",
        "workspace_memory_read",
        "workspace_memory_written",
        "compaction_started",
        "compaction_completed",
        "session_titled",
        "hook_invoked",
        "hook_blocked",
        "hook_failed",
        "model_call",
    }
)


_ENV_KEYS: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "google": "GOOGLE_API_KEY",
    "simple": "",
}

# Friendly display names for catalog model_ids. Anything not on this map
# falls back to the bare model_id.
_MODEL_LABELS: dict[str, str] = {
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "gpt-5-mini": "GPT-5 Mini",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-3-flash-preview": "Gemini 3 Flash (Preview)",
    "simple": "Simple (local)",
}

_PROVIDER_TO_BACKEND: dict[str, str] = {
    "deepseek": "deepseek",
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "gemini",
    "gemini": "gemini",
}

_EFFORT_LEVELS_BY_SCHEMA: dict[str, list[str]] = {
    # Anthropic uses level enums.
    "level": ["low", "medium", "high"],
    # Gemini uses int budget; UI shows preset buckets.
    "budget": ["low", "medium", "high"],
    "none": [],
}

# OpenAI Responses API uses a fixed enum even though catalog says ``none``.
_OPENAI_EFFORTS = ["minimal", "low", "medium", "high"]


@dataclass
class WebRuntime:
    loop: HarnessLoop
    model_backend: str
    workspace_root: Path
    default_max_steps: int = DEFAULT_MAX_STEPS
    trace_hub: TraceHub | None = None
    trace_path: Path | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    operator_config: Any | None = None  # OperatorConfig, typed as Any to avoid import cycle
    _locks: dict[str, threading.Lock] = field(default_factory=dict)
    _global: threading.Lock = field(default_factory=threading.Lock)
    _model_lock: threading.Lock = field(default_factory=threading.Lock)

    def lock_for(self, session_id: str) -> threading.Lock:
        with self._global:
            if session_id not in self._locks:
                self._locks[session_id] = threading.Lock()
            return self._locks[session_id]

    def available_models(self) -> list[dict[str, Any]]:
        import os

        from harnesslab.providers.catalog import ModelCatalog  # noqa: PLC0415
        from harnesslab.providers.model_resolve import (  # noqa: PLC0415
            resolve_anthropic_model_name,
            resolve_deepseek_model_name,
            resolve_gemini_model_name,
            resolve_openai_model_name,
        )

        catalog = ModelCatalog()
        cfg = self.operator_config
        current_by_backend = {
            "deepseek": resolve_deepseek_model_name(config=cfg),
            "anthropic": resolve_anthropic_model_name(config=cfg),
            "openai": resolve_openai_model_name(config=cfg),
            "gemini": resolve_gemini_model_name(config=cfg),
        }
        out: list[dict[str, Any]] = []
        for model_id in catalog.list_model_ids():
            entry = catalog.get(model_id)
            backend = _PROVIDER_TO_BACKEND.get(entry.provider, entry.provider)
            env_key = _ENV_KEYS.get(backend, "")
            configured = bool(env_key) and bool(os.environ.get(env_key, "").strip())
            is_current = (
                backend == self.model_backend
                and current_by_backend.get(backend) == model_id
            )
            effort_levels = self._effort_levels_for(backend, entry.thinking_schema)
            out.append(
                {
                    "id": model_id,
                    "provider": entry.provider,
                    "backend": backend,
                    "label": _MODEL_LABELS.get(model_id, model_id),
                    "context_window": entry.context_window,
                    "reasoning_support": entry.reasoning_support,
                    "thinking_schema": entry.thinking_schema,
                    "thinking_default": entry.thinking_default,
                    "effort_levels": effort_levels,
                    "configured": configured,
                    "current": is_current,
                    "current_effort": self._current_effort(backend) if is_current else None,
                }
            )
        # Append the deterministic local fallback so users can always pick it.
        out.append(
            {
                "id": "simple",
                "provider": "local",
                "backend": "simple",
                "label": _MODEL_LABELS["simple"],
                "context_window": 0,
                "reasoning_support": "none",
                "thinking_schema": "none",
                "thinking_default": "disabled",
                "effort_levels": [],
                "configured": True,
                "current": self.model_backend == "simple",
                "current_effort": None,
            }
        )
        return out

    @staticmethod
    def _effort_levels_for(backend: str, thinking_schema: str) -> list[str]:
        if backend == "openai":
            return list(_OPENAI_EFFORTS)
        if backend == "anthropic":
            return list(_EFFORT_LEVELS_BY_SCHEMA["level"])
        if backend == "gemini":
            return list(_EFFORT_LEVELS_BY_SCHEMA["budget"])
        return list(_EFFORT_LEVELS_BY_SCHEMA.get(thinking_schema, []))

    def _current_effort(self, backend: str) -> str | None:
        cfg = self.operator_config
        if cfg is None:
            return None
        if backend == "openai":
            return getattr(cfg, "openai_reasoning_effort", None) or None
        if backend == "anthropic":
            return getattr(cfg, "anthropic_thinking_effort", None) or None
        if backend == "gemini":
            return getattr(cfg, "gemini_thinking_level", None) or None
        if backend == "deepseek":
            return getattr(cfg, "deepseek_thinking", None) or None
        return None

    def switch_model(
        self,
        *,
        backend: str | None = None,
        model_id: str | None = None,
        effort: str | None = None,
    ) -> None:
        """Hot-swap the model in the running loop (thread-safe).

        - ``backend`` (optional): provider backend id (deepseek / openai / ...)
        - ``model_id`` (optional): concrete catalog entry to pin
        - ``effort`` (optional): reasoning effort / thinking level for the
          backend; semantics depend on provider.
        """

        from dataclasses import replace  # noqa: PLC0415

        from harnesslab.cli import _make_dynamic_blocks_provider  # noqa: PLC0415
        from harnesslab.providers.deepseek import tool_specs_from_registry  # noqa: PLC0415
        from harnesslab.providers.registry import create_model, normalize_backend  # noqa: PLC0415

        # Resolve target backend either explicitly or via model_id → provider.
        if backend:
            norm = normalize_backend(backend)
        elif model_id:
            try:
                from harnesslab.providers.catalog import ModelCatalog  # noqa: PLC0415

                entry = ModelCatalog().get(model_id)
                norm = _PROVIDER_TO_BACKEND.get(entry.provider, entry.provider)
            except KeyError:
                raise ValueError(f"unknown model: {model_id}") from None
        else:
            raise ValueError("either 'backend' or 'model_id' must be provided")

        with self._model_lock:
            # Apply config tweaks before constructing the new model.
            if self.operator_config is not None:
                cfg = self.operator_config
                changes: dict[str, Any] = {}
                if norm == "deepseek":
                    if model_id:
                        changes["deepseek_model_name"] = model_id
                    if effort:
                        changes["deepseek_thinking"] = effort
                elif norm == "anthropic":
                    if model_id:
                        changes["anthropic_model_name"] = model_id
                    if effort:
                        changes["anthropic_thinking_effort"] = effort
                        changes["anthropic_thinking"] = "enabled"
                elif norm == "openai":
                    if model_id:
                        changes["openai_model_name"] = model_id
                    if effort:
                        changes["openai_reasoning_effort"] = effort
                elif norm == "gemini":
                    if model_id:
                        changes["gemini_model_name"] = model_id
                    if effort:
                        changes["gemini_thinking_level"] = effort
                if changes:
                    self.operator_config = replace(cfg, **changes)

            model = create_model(
                norm,
                config=self.operator_config,
                tool_specs_provider=lambda: tool_specs_from_registry(
                    self.loop._tools.list()  # noqa: SLF001
                ),
                dynamic_blocks_provider=_make_dynamic_blocks_provider(
                    self.workspace_root,
                    self.loop._tools,  # noqa: SLF001
                    skill_selection_mode="heuristic",
                    planning_mode="off",
                ),
            )
            self.loop._model = model  # noqa: SLF001
            self.model_backend = norm
            self.settings["model_backend"] = norm


def _session_json(session: Session, *, memory_notes: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": session.id,
        "goal": session.goal,
        "title": session.title,
        "status": session.status,
        "turn_count": session.turn_count,
        "step_count": session.step_count,
        "created_at": session.created_at.isoformat(),
        "last_step_at": session.last_step_at.isoformat() if session.last_step_at else None,
        "parent_session_id": session.parent_session_id,
        "message_count": len(session.messages),
        "budget_usage": session.budget_usage.model_dump(mode="json"),
    }
    if memory_notes is not None:
        payload["memory_notes"] = memory_notes
    return payload


def _message_json(msg) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
    }


def _trace_event_json(event: TraceEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


def _tool_card_json(event: TraceEvent) -> dict[str, Any]:
    payload = event.payload
    return {
        "tool": payload.get("tool"),
        "ok": payload.get("ok", True),
        "error": payload.get("error"),
        "output_preview": payload.get("output_preview", ""),
        "output_truncated": payload.get("output_truncated", False),
        "duration_ms": payload.get("duration_ms"),
    }


def _tool_cards_for_turn(events: list[TraceEvent], turn_index: int) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    capturing = False
    for event in events:
        if event.event_type == "user_input_received":
            if event.payload.get("turn_index") == turn_index:
                capturing = True
                cards = []
            elif capturing:
                break
        if capturing and event.event_type == "tool_executed":
            cards.append(_tool_card_json(event))
    return cards


def _session_trace_events(runtime: WebRuntime, session_id: str) -> list[TraceEvent]:
    path = runtime.trace_path
    if path is None or not path.is_file():
        return []
    return [e for e in read_trace(path) if e.session_id == session_id]


def _memory_notes_for(loop: HarnessLoop, session_id: str) -> str | None:
    memory = getattr(loop, "_memory", None)
    if memory is None:
        return None
    return memory.get(session_memory_key(session_id))


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON body: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _wants_sse(handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> bool:
    accept = handler.headers.get("Accept", "")
    if "text/event-stream" in accept:
        return True
    return bool(body.get("stream"))


def _truncate_text(text: str, *, limit: int = _GATE_OUTPUT_LIMIT) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _run_gate_command(
    workspace_root: Path,
    *,
    gate: str,
) -> dict[str, Any]:
    commands: dict[str, list[str]] = {
        "pytest": ["uv", "run", "pytest"],
        "eval": ["uv", "run", "harnesslab", "eval"],
    }
    if gate not in commands:
        raise ValueError("gate must be one of: pytest, eval")
    argv = commands[gate]
    started = time.perf_counter()
    try:
        completed = subprocess.run(  # noqa: S603
            argv,
            cwd=workspace_root,
            text=True,
            capture_output=True,
            timeout=_GATE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        timeout_stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        timeout_stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        stdout, out_truncated = _truncate_text(timeout_stdout)
        stderr, err_truncated = _truncate_text(timeout_stderr)
        return {
            "gate": gate,
            "ok": False,
            "exit_code": None,
            "elapsed_ms": elapsed_ms,
            "command": argv,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": out_truncated,
            "stderr_truncated": err_truncated,
            "timed_out": True,
        }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    stdout, out_truncated = _truncate_text(completed.stdout or "")
    stderr, err_truncated = _truncate_text(completed.stderr or "")
    return {
        "gate": gate,
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "elapsed_ms": elapsed_ms,
        "command": argv,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": out_truncated,
        "stderr_truncated": err_truncated,
    }


class _Handler(BaseHTTPRequestHandler):
    runtime: WebRuntime

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._dispatch_get()
        except ValueError as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        except KeyError as exc:
            self._json_error(HTTPStatus.NOT_FOUND, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._dispatch_post()
        except ValueError as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        except KeyError as exc:
            self._json_error(HTTPStatus.NOT_FOUND, str(exc))

    def _dispatch_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._serve_static("index.html")
        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            return self._serve_static(rel)
        if path.startswith("/assets/"):
            # Vite bundles reference hashed assets from /assets/* at the web root.
            rel = path.lstrip("/")
            return self._serve_static(rel)

        if path == "/api/settings":
            return self._json_ok({"settings": self.runtime.settings})

        if path == "/api/proposals":
            qs = parse_qs(parsed.query)
            status = qs.get("status", ["open"])[0]
            proposals = _load_proposals(self.runtime.workspace_root, status=status)
            return self._json_ok({"proposals": proposals})

        if path.startswith("/api/proposals/"):
            proposal_id = path[len("/api/proposals/") :].strip("/")
            if not proposal_id:
                raise ValueError("proposal id required")
            proposal = _load_one_proposal(self.runtime.workspace_root, proposal_id)
            if proposal is None:
                raise KeyError("proposal not found")
            return self._json_ok({"proposal": proposal})

        if path == "/api/health":
            from harnesslab.providers.model_resolve import (  # noqa: PLC0415
                resolve_anthropic_model_name,
                resolve_deepseek_model_name,
                resolve_gemini_model_name,
                resolve_openai_model_name,
            )

            backend = self.runtime.model_backend
            cfg = self.runtime.operator_config
            model_id: str | None = None
            if backend == "deepseek":
                model_id = resolve_deepseek_model_name(config=cfg)
            elif backend == "anthropic":
                model_id = resolve_anthropic_model_name(config=cfg)
            elif backend == "openai":
                model_id = resolve_openai_model_name(config=cfg)
            elif backend == "gemini":
                model_id = resolve_gemini_model_name(config=cfg)
            return self._json_ok(
                {
                    "ok": True,
                    "model": backend,
                    "model_id": model_id,
                    "model_label": _MODEL_LABELS.get(model_id or "", model_id or backend),
                    "workspace": str(self.runtime.workspace_root),
                }
            )

        if path == "/api/models":
            return self._json_ok({"models": self.runtime.available_models()})

        if path.startswith("/api/sessions/") and path.endswith("/context"):
            remainder = path[len("/api/sessions/") :]
            session_id = remainder[: -len("/context")].strip("/")
            if not session_id:
                raise ValueError("session id required")
            snapshot = _last_context_snapshot(self.runtime, session_id)
            return self._json_ok({"context": snapshot})

        if path == "/api/sessions":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["50"])[0])
            status = qs.get("status", [None])[0]
            rows = self.runtime.loop._sessions.list(limit=limit, status=status)  # noqa: SLF001
            return self._json_ok({"sessions": [_session_json(s) for s in rows]})

        if path.startswith("/api/sessions/"):
            remainder = path[len("/api/sessions/") :].strip("/")
            if not remainder or "/" not in remainder:
                session_id = remainder
                if not session_id:
                    raise ValueError("invalid session path")
                session = self.runtime.loop._sessions.get(session_id)  # noqa: SLF001
                notes = _memory_notes_for(self.runtime.loop, session_id)
                return self._json_ok(
                    {
                        "session": _session_json(session, memory_notes=notes),
                        "messages": [_message_json(m) for m in session.messages],
                    }
                )
            session_id, action = remainder.split("/", 1)
            if action == "trace":
                events = self._trace_events_for(session_id)
                filtered = [
                    _trace_event_json(e)
                    for e in events
                    if e.event_type in TOOL_PANEL_EVENT_TYPES
                ]
                return self._json_ok({"session_id": session_id, "events": filtered})
            raise ValueError("invalid session path")

        self._json_error(HTTPStatus.NOT_FOUND, "not found")

    def _dispatch_post(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = _read_json(self)
        stream = _wants_sse(self, body)

        if path.startswith("/api/proposals/") and path.endswith("/status"):
            proposal_id = path[len("/api/proposals/") : -len("/status")].strip("/")
            if not proposal_id:
                raise ValueError("proposal id required")
            status = str(body.get("status", "")).strip()
            decision_note = str(body.get("decision_note", "")).strip()
            superseded_by = str(body.get("superseded_by", "")).strip()
            updated = _update_proposal_status(
                self.runtime.workspace_root,
                proposal_id,
                new_status=status,
                decision_note=decision_note,
                superseded_by=superseded_by,
                confirm_reviewed=bool(body.get("confirm_reviewed")),
                confirm_pytest_green=bool(body.get("confirm_pytest_green")),
                confirm_eval_no_regression=bool(body.get("confirm_eval_no_regression")),
            )
            return self._json_ok({"proposal": updated})

        if path == "/api/proposals/gates/run":
            gate = str(body.get("gate", "")).strip().lower()
            result = _run_gate_command(self.runtime.workspace_root, gate=gate)
            return self._json_ok({"result": result})

        if path == "/api/sessions":
            message = str(body.get("message", "")).strip()
            if not message:
                raise ValueError("message is required")
            max_steps = int(body.get("max_steps", self.runtime.default_max_steps))
            session = self.runtime.loop.start(goal=message)
            if stream:
                return self._run_turn_sse(
                    session_id=session.id,
                    message=message,
                    max_steps=max_steps,
                    is_new=True,
                )
            lock = self.runtime.lock_for(session.id)
            with lock:
                reply = self.runtime.loop.run_session(session.id, message, max_steps=max_steps)
                session = self.runtime.loop._sessions.get(session.id)  # noqa: SLF001
            return self._json_ok(self._turn_payload(session, reply))

        if path.startswith("/api/sessions/"):
            remainder = path[len("/api/sessions/") :].strip("/")
            if remainder.endswith("/messages"):
                session_id = remainder[: -len("/messages")].strip("/")
                if not session_id:
                    raise ValueError("session id required")
                message = str(body.get("message", "")).strip()
                if not message:
                    raise ValueError("message is required")
                max_steps = int(body.get("max_steps", self.runtime.default_max_steps))
                if stream:
                    return self._run_turn_sse(
                        session_id=session_id,
                        message=message,
                        max_steps=max_steps,
                        is_new=False,
                    )
                lock = self.runtime.lock_for(session_id)
                with lock:
                    self.runtime.loop._sessions.get(session_id)  # noqa: SLF001
                    reply = self.runtime.loop.run_session(
                        session_id, message, max_steps=max_steps
                    )
                    session = self.runtime.loop._sessions.get(session_id)  # noqa: SLF001
                return self._json_ok(self._turn_payload(session, reply))

            if remainder.endswith("/fork"):
                session_id = remainder[: -len("/fork")].strip("/")
                if not session_id:
                    raise ValueError("session id required")
                goal = body.get("goal")
                goal_str = str(goal).strip() if goal is not None else None
                lock = self.runtime.lock_for(session_id)
                with lock:
                    self.runtime.loop._sessions.get(session_id)  # noqa: SLF001
                    forked = self.runtime.loop.fork(
                        session_id,
                        goal=goal_str or None,
                    )
                return self._json_ok({"session": _session_json(forked)})

        if path == "/api/model":
            backend = str(body.get("backend", "")).strip() or None
            model_id = str(body.get("model_id", "")).strip() or None
            effort = str(body.get("effort", "")).strip() or None
            if not backend and not model_id:
                raise ValueError("either 'backend' or 'model_id' is required")
            try:
                self.runtime.switch_model(
                    backend=backend, model_id=model_id, effort=effort
                )
            except Exception as exc:  # noqa: BLE001
                raise ValueError(str(exc)) from exc
            return self._json_ok({"model": self.runtime.model_backend})

        self._json_error(HTTPStatus.NOT_FOUND, "not found")

    def _turn_payload(self, session: Session, reply: str) -> dict[str, Any]:
        notes = _memory_notes_for(self.runtime.loop, session.id)
        finished_turn = max(session.turn_count - 1, 0)
        trace_events = _session_trace_events(self.runtime, session.id)
        tool_cards = _tool_cards_for_turn(trace_events, finished_turn)
        context_snapshot = _last_context_snapshot(self.runtime, session.id)
        return {
            "session": _session_json(session, memory_notes=notes),
            "reply": reply,
            "messages": [_message_json(m) for m in session.messages],
            "tool_cards": tool_cards,
            "context_snapshot": context_snapshot,
        }

    def _run_turn_sse(
        self,
        *,
        session_id: str,
        message: str,
        max_steps: int,
        is_new: bool,
    ) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        write = self._sse_writer()
        hub = self.runtime.trace_hub

        def on_event(event: TraceEvent) -> None:
            if event.session_id != session_id:
                return
            if event.event_type not in TOOL_PANEL_EVENT_TYPES:
                return
            write("trace", _trace_event_json(event))

        if hub is not None:
            hub.subscribe(on_event)
        lock = self.runtime.lock_for(session_id)
        try:
            with lock:
                if not is_new:
                    self.runtime.loop._sessions.get(session_id)  # noqa: SLF001
                reply = self.runtime.loop.run_session(
                    session_id, message, max_steps=max_steps
                )
                session = self.runtime.loop._sessions.get(session_id)  # noqa: SLF001
            write("done", self._turn_payload(session, reply))
        except Exception as exc:  # noqa: BLE001 — surface to browser
            write("error", {"message": str(exc)})
        finally:
            if hub is not None:
                hub.unsubscribe(on_event)

    def _sse_writer(self) -> Callable[[str, dict[str, Any]], None]:
        def write(event: str, data: dict[str, Any]) -> None:
            payload = json.dumps(data, ensure_ascii=True)
            chunk = f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
            self.wfile.write(chunk)
            self.wfile.flush()

        return write

    def _trace_events_for(self, session_id: str) -> list[TraceEvent]:
        return _session_trace_events(self.runtime, session_id)

    def _serve_static(self, rel: str) -> None:
        static_dir = _select_static_dir()
        safe = Path(rel)
        if safe.is_absolute() or ".." in safe.parts:
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        file_path = (static_dir / safe).resolve()
        if not str(file_path).startswith(str(static_dir.resolve())):
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        if not file_path.is_file():
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        content = file_path.read_bytes()
        ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        # ``index.html`` references hash-suffixed assets in ``/assets/`` so the
        # assets themselves can stay immutable, but the HTML must not be
        # cached or browsers will keep pointing at the previous build's
        # filenames after the operator restarts ``harnesslab serve``.
        if file_path.suffix.lower() == ".html":
            self.send_header("Cache-Control", "no-store, max-age=0")
        elif "/assets/" in str(file_path).replace("\\", "/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(content)

    def _json_ok(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_error(self, status: HTTPStatus, message: str) -> None:
        data = json.dumps({"error": message}, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(
    runtime: WebRuntime,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
) -> None:
    """Block and serve until interrupted."""

    handler_cls = type(
        "BoundHandler",
        (_Handler,),
        {"runtime": runtime},
    )
    server = ThreadingHTTPServer((host, port), handler_cls)
    url = f"http://{host}:{port}/"
    _log.info("web ui listening url=%s", url)
    print(f"HarnessLab Web UI at {url}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


def _select_static_dir() -> Path:
    requested = os.environ.get("HARNESSLAB_WEB_UI_VERSION", "ts").strip().lower()
    if requested == "legacy":
        return _LEGACY_STATIC_DIR
    if _TS_STATIC_DIR.is_dir():
        return _TS_STATIC_DIR
    return _LEGACY_STATIC_DIR


def _last_context_snapshot(
    runtime: "WebRuntime", session_id: str
) -> dict[str, Any] | None:
    """Return the context payload from the most recent model_call trace event."""
    events = _session_trace_events(runtime, session_id)
    for event in reversed(events):
        if event.event_type == "model_call":
            ctx = event.payload.get("context")
            if isinstance(ctx, dict):
                return ctx
    return None


def _load_proposals(workspace_root: Path, *, status: str = "open") -> list[dict[str, Any]]:
    proposals_dir = workspace_root / "proposals"
    if not proposals_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(proposals_dir.glob("prop_*.md"), reverse=True):
        parsed = _parse_proposal_markdown(path)
        if parsed is None:
            continue
        if status != "all" and parsed.get("status") != status:
            continue
        out.append(
            {
                "id": parsed.get("id"),
                "status": parsed.get("status"),
                "kind": parsed.get("kind"),
                "cluster_signature": parsed.get("cluster_signature"),
                "occurrences": parsed.get("occurrences"),
                "generated_at": parsed.get("generated_at"),
            }
        )
    return out


def _load_one_proposal(workspace_root: Path, proposal_id: str) -> dict[str, Any] | None:
    proposals_dir = workspace_root / "proposals"
    path = proposals_dir / f"{proposal_id}.md"
    if not path.is_file():
        return None
    parsed = _parse_proposal_markdown(path)
    if parsed is None:
        return None
    return {
        "id": parsed.get("id"),
        "status": parsed.get("status"),
        "kind": parsed.get("kind"),
        "cluster_signature": parsed.get("cluster_signature"),
        "occurrences": parsed.get("occurrences"),
        "generated_at": parsed.get("generated_at"),
        "superseded_by": parsed.get("superseded_by"),
        "related_files": parsed.get("related_files", []),
        "body_markdown": parsed.get("body_markdown", ""),
    }


def _proposal_path(workspace_root: Path, proposal_id: str) -> Path:
    return workspace_root / "proposals" / f"{proposal_id}.md"


def _update_proposal_status(
    workspace_root: Path,
    proposal_id: str,
    *,
    new_status: str,
    decision_note: str = "",
    superseded_by: str = "",
    confirm_reviewed: bool = False,
    confirm_pytest_green: bool = False,
    confirm_eval_no_regression: bool = False,
) -> dict[str, Any]:
    if new_status not in {"open", "accepted", "rejected", "superseded"}:
        raise ValueError("status must be one of: open, accepted, rejected, superseded")
    path = _proposal_path(workspace_root, proposal_id)
    if not path.is_file():
        raise KeyError("proposal not found")
    parsed = _parse_proposal_markdown(path)
    if parsed is None:
        raise ValueError("invalid proposal markdown format")

    if new_status == "accepted":
        if not (confirm_reviewed and confirm_pytest_green and confirm_eval_no_regression):
            raise ValueError(
                "accepted requires confirm_reviewed, confirm_pytest_green, and "
                "confirm_eval_no_regression all true"
            )
    if new_status == "rejected" and not decision_note.strip():
        raise ValueError("rejected requires non-empty decision_note")
    if new_status == "superseded" and not superseded_by.strip():
        raise ValueError("superseded requires non-empty superseded_by")

    parsed["status"] = new_status
    if new_status == "superseded":
        parsed["superseded_by"] = superseded_by.strip()

    body = str(parsed.get("body_markdown", "")).strip()
    if new_status == "rejected":
        body = _upsert_section(body, "Decision", decision_note.strip())
    elif new_status == "superseded":
        body = _upsert_section(body, "Superseded By", superseded_by.strip())
    elif new_status == "accepted":
        acceptance = (
            "- reviewed_by_human: true\n"
            "- pytest_green: true\n"
            "- eval_no_regression: true"
        )
        body = _upsert_section(body, "Acceptance Checklist", acceptance)
    parsed["body_markdown"] = body
    path.write_text(_render_proposal_markdown(parsed), encoding="utf-8")

    updated = _load_one_proposal(workspace_root, proposal_id)
    if updated is None:
        raise ValueError("failed to reload updated proposal")
    return updated


def _parse_proposal_markdown(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    front = lines[1:end]
    body = "\n".join(lines[end + 1 :]).strip()
    parsed: dict[str, Any] = {"related_files": []}
    idx = 0
    while idx < len(front):
        line = front[idx]
        if line.startswith("related_files:"):
            idx += 1
            related: list[str] = []
            while idx < len(front) and front[idx].lstrip().startswith("- "):
                related.append(front[idx].split("- ", 1)[1].strip())
                idx += 1
            parsed["related_files"] = related
            continue
        if ":" in line:
            key, raw = line.split(":", 1)
            value = raw.strip().strip('"')
            parsed[key.strip()] = value
        idx += 1
    if "id" not in parsed:
        parsed["id"] = path.stem
    occurrences = parsed.get("occurrences")
    if isinstance(occurrences, str) and occurrences.isdigit():
        parsed["occurrences"] = int(occurrences)
    parsed["body_markdown"] = body
    return parsed


def _render_proposal_markdown(parsed: dict[str, Any]) -> str:
    related_files = parsed.get("related_files") or []
    if not isinstance(related_files, list):
        related_files = []

    ordered_keys = [
        "id",
        "status",
        "kind",
        "cluster_signature",
        "occurrences",
        "generated_at",
        "superseded_by",
    ]
    lines = ["---"]
    for key in ordered_keys:
        value = parsed.get(key)
        if value is None or value == "":
            continue
        lines.append(f"{key}: {value}")
    lines.append("related_files:")
    for item in related_files:
        lines.append(f"  - {item}")
    lines.append("---")
    lines.append("")
    body = str(parsed.get("body_markdown", "")).strip()
    if body:
        lines.append(body)
    return "\n".join(lines) + "\n"


def _upsert_section(body: str, heading: str, section_body: str) -> str:
    marker = f"## {heading}"
    chunks = body.split("\n")
    start = -1
    end = len(chunks)
    for idx, line in enumerate(chunks):
        if line.strip() == marker:
            start = idx
            continue
        if start >= 0 and line.startswith("## "):
            end = idx
            break
    replacement = [marker, "", section_body.strip()]
    if start >= 0:
        chunks = chunks[:start] + replacement + chunks[end:]
        return "\n".join(chunks).strip()
    if not body.strip():
        return "\n".join(replacement).strip()
    return f"{body.strip()}\n\n{marker}\n\n{section_body.strip()}".strip()
