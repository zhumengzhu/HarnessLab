"""Localhost HTTP server + JSON API for the chat Web UI."""

from __future__ import annotations

import json
import mimetypes
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from harnesslab.core.loop import DEFAULT_MAX_STEPS, HarnessLoop
from harnesslab.core.models import Session

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass
class WebRuntime:
    loop: HarnessLoop
    model_backend: str
    workspace_root: Path
    default_max_steps: int = DEFAULT_MAX_STEPS
    _locks: dict[str, threading.Lock] = field(default_factory=dict)
    _global: threading.Lock = field(default_factory=threading.Lock)

    def lock_for(self, session_id: str) -> threading.Lock:
        with self._global:
            if session_id not in self._locks:
                self._locks[session_id] = threading.Lock()
            return self._locks[session_id]


def _session_json(session: Session) -> dict[str, Any]:
    return {
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


def _message_json(msg) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
    }


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


class _Handler(BaseHTTPRequestHandler):
    runtime: WebRuntime

    def log_message(self, fmt: str, *args: object) -> None:
        # Quiet default access log; CLI users see their own prints.
        return

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._dispatch_get()
        except ValueError as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))

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
            session_id = path[len("/api/sessions/") :].strip("/")
            if not session_id or "/" in session_id:
                raise ValueError("invalid session path")
            session = self.runtime.loop._sessions.get(session_id)  # noqa: SLF001
            return self._json_ok(
                {
                    "session": _session_json(session),
                    "messages": [_message_json(m) for m in session.messages],
                }
            )

        self._json_error(HTTPStatus.NOT_FOUND, "not found")

    def _dispatch_post(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = _read_json(self)

        if path == "/api/sessions":
            message = str(body.get("message", "")).strip()
            if not message:
                raise ValueError("message is required")
            max_steps = int(body.get("max_steps", self.runtime.default_max_steps))
            session = self.runtime.loop.start(goal=message)
            lock = self.runtime.lock_for(session.id)
            with lock:
                reply = self.runtime.loop.run_session(session.id, message, max_steps=max_steps)
                session = self.runtime.loop._sessions.get(session.id)  # noqa: SLF001
            return self._json_ok(
                {
                    "session": _session_json(session),
                    "reply": reply,
                    "messages": [_message_json(m) for m in session.messages],
                }
            )

        if path.startswith("/api/sessions/") and path.endswith("/messages"):
            session_id = path[len("/api/sessions/") : -len("/messages")].strip("/")
            if not session_id:
                raise ValueError("session id required")
            message = str(body.get("message", "")).strip()
            if not message:
                raise ValueError("message is required")
            max_steps = int(body.get("max_steps", self.runtime.default_max_steps))
            lock = self.runtime.lock_for(session_id)
            with lock:
                self.runtime.loop._sessions.get(session_id)  # noqa: SLF001 — KeyError
                reply = self.runtime.loop.run_session(
                    session_id, message, max_steps=max_steps
                )
                session = self.runtime.loop._sessions.get(session_id)  # noqa: SLF001
            return self._json_ok(
                {
                    "session": _session_json(session),
                    "reply": reply,
                    "messages": [_message_json(m) for m in session.messages],
                }
            )

        self._json_error(HTTPStatus.NOT_FOUND, "not found")

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
