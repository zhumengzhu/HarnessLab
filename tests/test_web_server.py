"""Tests for the Phase 3.2 Web UI HTTP server."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from harnesslab.cli import build_runtime
from harnesslab.core.operator_config import OperatorConfig, config_settings_snapshot
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder
from harnesslab.web.server import WebRuntime, serve
from harnesslab.web.trace_hub import TraceHub


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _get(url: str, *, retries: int = 20) -> dict:
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionResetError) as exc:
            last_err = exc
            time.sleep(0.05)
    raise last_err  # type: ignore[misc]


def _post(url: str, payload: dict, *, retries: int = 20, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(  # noqa: S310
                url,
                data=data,
                headers=hdrs,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionResetError) as exc:
            last_err = exc
            time.sleep(0.05)
    raise last_err  # type: ignore[misc]


def _post_sse(url: str, payload: dict) -> str:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def _web_runtime(tmp_path: Path, *, max_steps: int = 1) -> WebRuntime:
    (tmp_path / ".harnesslab").mkdir(parents=True, exist_ok=True)
    trace_path = tmp_path / ".harnesslab" / "trace.jsonl"
    hub = TraceHub(JsonlTraceRecorder(trace_path))
    loop = build_runtime(
        tmp_path,
        storage_backend="sqlite",
        model_backend="simple",
        trace=hub,
    )
    return WebRuntime(
        loop=loop,
        model_backend="simple",
        workspace_root=tmp_path,
        default_max_steps=max_steps,
        trace_hub=hub,
        trace_path=trace_path,
        settings=config_settings_snapshot(
            OperatorConfig(model_backend="simple"),
            workspace_root=tmp_path,
            model_backend="simple",
        ),
    )


def _start_server(runtime: WebRuntime, port: int) -> None:
    thread = threading.Thread(
        target=serve,
        kwargs={"runtime": runtime, "host": "127.0.0.1", "port": port},
        daemon=True,
    )
    thread.start()


def test_web_api_create_session_and_list(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)

    base = f"http://127.0.0.1:{port}"
    health = _get(f"{base}/api/health")
    assert health["ok"] is True
    assert health["model"] == "simple"

    created = _post(f"{base}/api/sessions", {"message": "hello web"})
    session_id = created["session"]["id"]
    assert created["reply"]
    assert any(m["role"] == "user" for m in created["messages"])

    listed = _get(f"{base}/api/sessions")
    assert any(s["id"] == session_id for s in listed["sessions"])

    detail = _get(f"{base}/api/sessions/{session_id}")
    assert detail["session"]["id"] == session_id
    assert len(detail["messages"]) >= 1

    continued = _post(
        f"{base}/api/sessions/{session_id}/messages",
        {"message": "again"},
    )
    assert continued["session"]["turn_count"] >= 1


def test_web_remember_and_memory_notes(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "start"})
    session_id = created["session"]["id"]
    remembered = _post(
        f"{base}/api/sessions/{session_id}/messages",
        {"message": "/remember api prefers json"},
    )
    assert remembered["reply"] == "Stored in session memory."
    detail = _get(f"{base}/api/sessions/{session_id}")
    assert detail["session"]["memory_notes"]
    assert "api prefers json" in detail["session"]["memory_notes"]


def test_web_fork_session(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "parent"})
    parent_id = created["session"]["id"]
    forked = _post(f"{base}/api/sessions/{parent_id}/fork", {})
    assert forked["session"]["id"] != parent_id
    assert forked["session"]["parent_session_id"] == parent_id


def test_web_sse_stream_returns_done_event(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    body = _post_sse(f"{base}/api/sessions", {"message": "stream me", "stream": True})
    assert "event: done" in body


def test_web_trace_endpoint(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path, max_steps=1)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "trace probe"})
    session_id = created["session"]["id"]
    trace = _get(f"{base}/api/sessions/{session_id}/trace")
    assert trace["session_id"] == session_id
    assert any(e["event_type"] == "decision_made" for e in trace["events"])


def test_web_settings_api(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    data = _get(f"{base}/api/settings")
    settings = data["settings"]
    assert settings["model_backend"] == "simple"
    assert settings["workspace"] == str(tmp_path.resolve())
    assert "shell_profile" in settings


def test_web_static_index_served(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    with urllib.request.urlopen(f"{base}/", timeout=5) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    assert "HarnessLab" in body
    assert "/static/app.js" in body
    assert "tool-panel" in body
