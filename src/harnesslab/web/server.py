"""Localhost HTTP server + JSON API for the chat Web UI."""

from __future__ import annotations

import json
import mimetypes
import threading
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
from harnesslab.web.trace_hub import TraceHub

_STATIC_DIR = Path(__file__).resolve().parent / "static"

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
    }
)


@dataclass
class WebRuntime:
    loop: HarnessLoop
    model_backend: str
    workspace_root: Path
    default_max_steps: int = DEFAULT_MAX_STEPS
    trace_hub: TraceHub | None = None
    trace_path: Path | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    _locks: dict[str, threading.Lock] = field(default_factory=dict)
    _global: threading.Lock = field(default_factory=threading.Lock)

    def lock_for(self, session_id: str) -> threading.Lock:
        with self._global:
            if session_id not in self._locks:
                self._locks[session_id] = threading.Lock()
            return self._locks[session_id]


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

        if path == "/api/settings":
            return self._json_ok({"settings": self.runtime.settings})

        if path == "/api/health":
            return self._json_ok(
                {
                    "ok": True,
                    "model": self.runtime.model_backend,
                    "workspace": str(self.runtime.workspace_root),
                }
            )

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

        self._json_error(HTTPStatus.NOT_FOUND, "not found")

    def _turn_payload(self, session: Session, reply: str) -> dict[str, Any]:
        notes = _memory_notes_for(self.runtime.loop, session.id)
        finished_turn = max(session.turn_count - 1, 0)
        trace_events = _session_trace_events(self.runtime, session.id)
        tool_cards = _tool_cards_for_turn(trace_events, finished_turn)
        return {
            "session": _session_json(session, memory_notes=notes),
            "reply": reply,
            "messages": [_message_json(m) for m in session.messages],
            "tool_cards": tool_cards,
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
        safe = Path(rel)
        if safe.is_absolute() or ".." in safe.parts:
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        file_path = (_STATIC_DIR / safe).resolve()
        if not str(file_path).startswith(str(_STATIC_DIR.resolve())):
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
    print(f"HarnessLab Web UI at {url}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
