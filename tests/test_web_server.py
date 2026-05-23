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
from harnesslab.web.server import WebRuntime, serve


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


def _post(url: str, payload: dict, *, retries: int = 20) -> dict:
    data = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(  # noqa: S310
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionResetError) as exc:
            last_err = exc
            time.sleep(0.05)
    raise last_err  # type: ignore[misc]


def test_web_api_create_session_and_list(tmp_path: Path) -> None:
    (tmp_path / ".harnesslab").mkdir(parents=True, exist_ok=True)
    port = _free_port()
    loop = build_runtime(tmp_path, storage_backend="sqlite", model_backend="simple")
    runtime = WebRuntime(
        loop=loop,
        model_backend="simple",
        workspace_root=tmp_path,
        default_max_steps=1,
    )

    thread = threading.Thread(
        target=serve,
        kwargs={"runtime": runtime, "host": "127.0.0.1", "port": port},
        daemon=True,
    )
    thread.start()

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


def test_web_static_index_served(tmp_path: Path) -> None:
    port = _free_port()
    loop = build_runtime(tmp_path, model_backend="simple")
    runtime = WebRuntime(
        loop=loop,
        model_backend="simple",
        workspace_root=tmp_path,
    )
    thread = threading.Thread(
        target=serve,
        kwargs={"runtime": runtime, "host": "127.0.0.1", "port": port},
        daemon=True,
    )
    thread.start()
    base = f"http://127.0.0.1:{port}"
    with urllib.request.urlopen(f"{base}/", timeout=5) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    assert "HarnessLab" in body
    assert "/static/app.js" in body
