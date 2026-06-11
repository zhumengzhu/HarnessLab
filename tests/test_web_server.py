"""Tests for the Phase 3.2 Web UI HTTP server."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import harnesslab.web.server as web_server
from harnesslab.cli import build_runtime
from harnesslab.core.operator_config import (
    OperatorConfig,
    config_settings_snapshot,
    load_operator_config,
)
from harnesslab.telemetry.local_span_recorder import LocalSpanRecorder
from harnesslab.telemetry.recorder_factory import default_spans_path
from harnesslab.web.server import WebRuntime, serve
from harnesslab.web.span_hub import SpanHub


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


_SERVER_RETRY_INTERVAL_S = 0.1
_DEFAULT_SERVER_RETRIES = 100


def _open_url(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    retries: int = _DEFAULT_SERVER_RETRIES,
) -> bytes:
    hdrs = headers or {}
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(  # noqa: S310
                url,
                data=data,
                headers=hdrs,
                method=method,
            )
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                return resp.read()
        except (urllib.error.URLError, ConnectionResetError) as exc:
            last_err = exc
            time.sleep(_SERVER_RETRY_INTERVAL_S)
    raise last_err  # type: ignore[misc]


def _get(url: str, *, retries: int = _DEFAULT_SERVER_RETRIES) -> dict:
    return json.loads(_open_url(url, retries=retries).decode("utf-8"))


def _post(
    url: str,
    payload: dict,
    *,
    retries: int = _DEFAULT_SERVER_RETRIES,
    headers: dict | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    body = _open_url(url, method="POST", data=data, headers=hdrs, retries=retries)
    return json.loads(body.decode("utf-8"))


def _post_sse(url: str, payload: dict, *, retries: int = _DEFAULT_SERVER_RETRIES) -> str:
    data = json.dumps(payload).encode("utf-8")
    body = _open_url(
        url,
        method="POST",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        retries=retries,
    )
    return body.decode("utf-8")


def _post_error(
    url: str,
    payload: dict,
    *,
    retries: int = _DEFAULT_SERVER_RETRIES,
) -> tuple[int, str]:
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
            with urllib.request.urlopen(req, timeout=30):  # noqa: S310
                return (200, "")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return (int(exc.code), body)
        except (urllib.error.URLError, ConnectionResetError) as exc:
            last_err = exc
            time.sleep(_SERVER_RETRY_INTERVAL_S)
    raise last_err  # type: ignore[misc]


def _patch(url: str, payload: dict, *, retries: int = _DEFAULT_SERVER_RETRIES) -> dict:
    data = json.dumps(payload).encode("utf-8")
    body = _open_url(
        url,
        method="PATCH",
        data=data,
        headers={"Content-Type": "application/json"},
        retries=retries,
    )
    return json.loads(body.decode("utf-8"))


def _web_runtime(tmp_path: Path, *, max_steps: int = 1) -> WebRuntime:
    (tmp_path / ".harnesslab").mkdir(parents=True, exist_ok=True)
    spans_path = default_spans_path(tmp_path)
    hub = SpanHub(LocalSpanRecorder(spans_path))
    loop = build_runtime(
        tmp_path,
        storage_backend="sqlite",
        model_backend="simple",
        spans=hub,
    )
    return WebRuntime(
        loop=loop,
        model_backend="simple",
        workspace_root=tmp_path,
        default_max_steps=max_steps,
        span_hub=hub,
        spans_path=spans_path,
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
    _get(f"http://127.0.0.1:{port}/api/health")


def test_web_api_models_deepseek_catalog_fields(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    runtime.model_backend = "deepseek"
    runtime.operator_config = OperatorConfig(
        model_backend="deepseek",
        deepseek_model_name="deepseek-v4-flash",
    )
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    models = _get(f"{base}/api/models")["models"]
    ds = next(m for m in models if m["id"] == "deepseek-v4-flash")
    assert ds["effort_levels"] == ["disabled", "high", "max"]
    assert ds["context_window"] == 1_048_576
    assert ds["context_label"] == "1M"
    assert ds["context_editable"] is False


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
    assert created["session"]["budget_usage"]["llm_calls_total"] >= 1

    listed = _get(f"{base}/api/sessions")
    assert any(s["id"] == session_id for s in listed["sessions"])

    detail = _get(f"{base}/api/sessions/{session_id}")
    assert detail["session"]["id"] == session_id
    assert len(detail["messages"]) >= 1
    assert "budget_usage" in detail["session"]

    continued = _post(
        f"{base}/api/sessions/{session_id}/messages",
        {"message": "again"},
    )
    assert continued["session"]["turn_count"] >= 1

    usage = _get(f"{base}/api/usage?range=all")
    assert usage["totals"]["llm_calls"] >= 1
    assert isinstance(usage["daily"], list)
    assert isinstance(usage["by_model"], list)
    assert isinstance(usage["sessions"], list)


def test_web_sessions_list_pins_include_id(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    older = _post(f"{base}/api/sessions", {"message": "older session"})
    older_id = older["session"]["id"]
    newer = _post(f"{base}/api/sessions", {"message": "newer session"})
    newer_id = newer["session"]["id"]

    listed = _get(f"{base}/api/sessions?limit=1")
    assert listed["sessions"][0]["id"] == newer_id

    pinned = _get(f"{base}/api/sessions?limit=1&include_id={older_id}")
    assert [s["id"] for s in pinned["sessions"]] == [older_id]


def test_web_usage_api(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    _post(f"{base}/api/sessions", {"message": "hello usage"})
    usage = _get(f"{base}/api/usage?range=all")
    assert usage["range"] == "all"
    assert usage["totals"]["llm_calls"] >= 1
    assert isinstance(usage["daily"], list)
    assert isinstance(usage["by_model"], list)
    assert isinstance(usage["sessions"], list)


def test_web_sessions_list_reports_persisted_message_count(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "hello"})
    session_id = created["session"]["id"]
    _post(f"{base}/api/sessions/{session_id}/messages", {"message": "again"})

    listed = _get(f"{base}/api/sessions?limit=5")
    row = next(item for item in listed["sessions"] if item["id"] == session_id)
    assert row["message_count"] > 0


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


def test_web_skill_command_roundtrip(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("deep research", encoding="utf-8")

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "start"})
    session_id = created["session"]["id"]

    listed = _post(
        f"{base}/api/sessions/{session_id}/messages",
        {"message": "/skill list"},
    )
    assert "Skills available:" in listed["reply"]
    assert "- research" in listed["reply"]

    selected = _post(
        f"{base}/api/sessions/{session_id}/messages",
        {"message": "/skill add research"},
    )
    assert "Selected skill 'research'" in selected["reply"]


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


def test_web_patch_session_title(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "rename me"})
    session_id = created["session"]["id"]
    updated = _patch(
        f"{base}/api/sessions/{session_id}",
        {"title": "Research thread"},
    )
    assert updated["session"]["title"] == "Research thread"

    listed = _get(f"{base}/api/sessions?limit=5")
    match = next(row for row in listed["sessions"] if row["id"] == session_id)
    assert match["title"] == "Research thread"


def test_web_patch_session_model_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "model": {
                    "default_backend": "simple",
                    "deepseek": {"model_name": "deepseek-v4-flash", "thinking": "disabled"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESSLAB_CONFIG", str(config_path))

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    runtime.operator_config = load_operator_config(config_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "model probe"})
    session_id = created["session"]["id"]
    updated = _patch(
        f"{base}/api/sessions/{session_id}",
        {
            "model_backend": "deepseek",
            "model_id": "deepseek-v4-pro",
            "effort": "max",
        },
    )
    assert updated["session"]["model_backend"] == "deepseek"
    assert updated["session"]["model_id"] == "deepseek-v4-pro"
    assert updated["session"]["model_effort"] == "max"

    reloaded = load_operator_config(config_path)
    assert reloaded.model_backend == "simple"
    assert reloaded.deepseek_model_name == "deepseek-v4-flash"

    cleared = _patch(f"{base}/api/sessions/{session_id}", {"model_backend": None})
    assert cleared["session"]["model_backend"] is None
    assert cleared["session"]["model_id"] is None
    assert cleared["session"]["model_effort"] is None


def test_web_fork_session_copies_model_override(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "parent"})
    parent_id = created["session"]["id"]
    _patch(
        f"{base}/api/sessions/{parent_id}",
        {"model_backend": "deepseek", "model_id": "deepseek-v4-pro", "effort": "high"},
    )
    forked = _post(f"{base}/api/sessions/{parent_id}/fork", {})
    assert forked["session"]["model_backend"] == "deepseek"
    assert forked["session"]["model_id"] == "deepseek-v4-pro"
    assert forked["session"]["model_effort"] == "high"


def test_web_steer_requires_active_turn(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "idle session"})
    session_id = created["session"]["id"]
    status, body = _post_error(
        f"{base}/api/sessions/{session_id}/steer",
        {"message": "steer while idle"},
    )
    assert status == 409
    assert "no active turn" in body


def test_web_runtime_submit_steer_while_active(tmp_path: Path) -> None:
    runtime = _web_runtime(tmp_path)
    session = runtime.loop.start(goal="active")
    with pytest.raises(ValueError, match="no active turn"):
        runtime.submit_steer(session.id, "too early")

    runtime.begin_turn(session.id)
    try:
        result = runtime.submit_steer(session.id, "mid-turn steer")
        assert result == {"ok": True, "queued": 1}
        assert runtime.turn_steer.pending_count(session.id) == 1
    finally:
        runtime.end_turn(session.id)
    assert runtime.turn_steer.pending_count(session.id) == 0


def test_web_sse_stream_returns_done_event(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    body = _post_sse(f"{base}/api/sessions", {"message": "stream me", "stream": True})
    assert "event: span.started" in body or "event: span.completed" in body
    assert "event: done" in body
    assert body.index("event: done") > 0


def _sse_event_names(body: str) -> list[str]:
    return [
        line.removeprefix("event: ").strip()
        for line in body.splitlines()
        if line.startswith("event: ")
    ]


def test_web_sse_stream_event_ordering(tmp_path: Path) -> None:
    """Trace fan-in events must precede the terminal done frame."""

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    body = _post_sse(f"{base}/api/sessions", {"message": "ordering probe", "stream": True})
    names = _sse_event_names(body)
    assert names, "expected SSE events"
    assert names[-1] == "done"
    assert any(name.startswith("span.") for name in names)
    assert names.index("done") == len(names) - 1
    assert "event: error" not in body


def test_web_checkpoints_list_preview_and_rewind(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path, max_steps=3)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    target = tmp_path / "rewind.txt"
    target.write_text("v1\n", encoding="utf-8")
    created = _post(
        f"{base}/api/sessions",
        {
            "message": '/tool write_file {"path": "rewind.txt", "content": "v2\\n"}',
            "max_steps": 2,
        },
    )
    session_id = created["session"]["id"]
    listed = _get(f"{base}/api/sessions/{session_id}/checkpoints")
    assert listed["checkpoints"], "expected at least one checkpoint"
    checkpoint_id = listed["checkpoints"][0]["id"]

    preview = _get(f"{base}/api/sessions/{session_id}/checkpoints/{checkpoint_id}")
    assert preview["changes"]
    assert preview["changes"][0]["path"] == "rewind.txt"

    result = _post(
        f"{base}/api/sessions/{session_id}/rewind",
        {"checkpoint_id": checkpoint_id, "confirm": True},
    )
    assert "rewind.txt" in result["paths"]
    assert target.read_text(encoding="utf-8") == "v1\n"


def test_web_trace_endpoint(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path, max_steps=1)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "trace probe"})
    session_id = created["session"]["id"]
    trace = _get(f"{base}/api/sessions/{session_id}/trace")
    assert trace["session_id"] == session_id
    assert any(s["name"] == "harnesslab.step" for s in trace["spans"])


def test_web_trace_jsonl_endpoint(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path, max_steps=1)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    created = _post(f"{base}/api/sessions", {"message": "jsonl probe"})
    session_id = created["session"]["id"]
    payload = _get(f"{base}/api/sessions/{session_id}/trace/jsonl")
    assert payload["session_id"] == session_id
    assert payload["line_count"] >= 1
    assert payload["jsonl"].strip()
    first = json.loads(payload["jsonl"].strip().split("\n")[0])
    assert first["session_id"] == session_id
    assert first["name"]


def test_web_artifact_endpoint(tmp_path: Path) -> None:
    from harnesslab.artifact.in_memory import InMemoryArtifactStore

    port = _free_port()
    runtime = _web_runtime(tmp_path, max_steps=1)
    runtime.loop._artifacts = InMemoryArtifactStore()  # noqa: SLF001
    store = runtime.loop._artifacts  # noqa: SLF001
    session = runtime.loop.start(goal="artifact probe")
    ref = store.put(
        b"full tool output body",
        mime="text/plain; charset=utf-8",
        session_id=session.id,
        artifact_id="art_web_test",
    )
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    payload = _get(f"{base}/api/sessions/{session.id}/artifacts/{ref}")
    assert payload["id"] == ref
    assert payload["encoding"] == "utf-8"
    assert payload["content"] == "full tool output body"

    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(f"{base}/api/sessions/{session.id}/artifacts/missing")
    assert exc.value.code == 404


def test_web_health_includes_pricing_fingerprint(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    health = _get(f"http://127.0.0.1:{port}/api/health")
    assert health["ok"] is True
    assert health.get("pricing_fingerprint")
    assert health.get("trace_path")


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


def test_web_proposals_api_list_and_detail(tmp_path: Path) -> None:
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    body = """---
id: prop_20260524_abcd1234
status: open
kind: policy_denial
cluster_signature: "tool_denied:run_shell_safe:command not in allowlist"
occurrences: 3
generated_at: 2026-05-24T00:00:00+00:00
related_files:
  - src/harnesslab/policy/default_policy.py
---

## Suggested actions

1. tighten shell profile
"""
    (proposals / "prop_20260524_abcd1234.md").write_text(body, encoding="utf-8")

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    listed = _get(f"{base}/api/proposals?status=open")
    assert len(listed["proposals"]) == 1
    assert listed["proposals"][0]["id"] == "prop_20260524_abcd1234"

    detail = _get(f"{base}/api/proposals/prop_20260524_abcd1234")
    assert detail["proposal"]["status"] == "open"
    assert "Suggested actions" in detail["proposal"]["body_markdown"]


def test_web_proposal_status_update_enforces_rules(tmp_path: Path) -> None:
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    body = """---
id: prop_20260524_abcd1234
status: open
kind: policy_denial
cluster_signature: "tool_denied:run_shell_safe:command not in allowlist"
occurrences: 3
generated_at: 2026-05-24T00:00:00+00:00
related_files:
  - src/harnesslab/policy/default_policy.py
---

## Suggested actions

1. tighten shell profile
"""
    (proposals / "prop_20260524_abcd1234.md").write_text(body, encoding="utf-8")

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    code, _ = _post_error(
        f"{base}/api/proposals/prop_20260524_abcd1234/status",
        {"status": "rejected"},
    )
    assert code == 400

    updated = _post(
        f"{base}/api/proposals/prop_20260524_abcd1234/status",
        {"status": "rejected", "decision_note": "False positive after manual triage."},
    )
    assert updated["proposal"]["status"] == "rejected"
    assert "## Decision" in updated["proposal"]["body_markdown"]

    listed_open = _get(f"{base}/api/proposals?status=open")
    assert listed_open["proposals"] == []

    listed_all = _get(f"{base}/api/proposals?status=all")
    assert len(listed_all["proposals"]) == 1
    assert listed_all["proposals"][0]["status"] == "rejected"


def test_web_proposal_accept_requires_gate_confirmations(tmp_path: Path) -> None:
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    body = """---
id: prop_20260524_accept123
status: open
kind: replay_divergence
cluster_signature: "replay:decision_mismatch"
occurrences: 2
generated_at: 2026-05-24T00:00:00+00:00
related_files:
  - src/harnesslab/replay/diff.py
---

## Suggested actions

1. tighten volatile compare set
"""
    (proposals / "prop_20260524_accept123.md").write_text(body, encoding="utf-8")

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    code, _ = _post_error(
        f"{base}/api/proposals/prop_20260524_accept123/status",
        {"status": "accepted"},
    )
    assert code == 400

    accepted = _post(
        f"{base}/api/proposals/prop_20260524_accept123/status",
        {
            "status": "accepted",
            "confirm_reviewed": True,
            "confirm_pytest_green": True,
            "confirm_eval_no_regression": True,
        },
    )
    assert accepted["proposal"]["status"] == "accepted"
    assert "## Acceptance Checklist" in accepted["proposal"]["body_markdown"]


def test_web_proposal_gate_run_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_gate(workspace_root: Path, *, gate: str) -> dict:
        assert workspace_root == tmp_path
        return {
            "gate": gate,
            "ok": True,
            "exit_code": 0,
            "elapsed_ms": 123,
            "command": ["uv", "run", gate],
            "stdout": "ok",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }

    monkeypatch.setattr(web_server, "_run_gate_command", _fake_gate)
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    result = _post(f"{base}/api/proposals/gates/run", {"gate": "pytest"})
    assert result["result"]["gate"] == "pytest"
    assert result["result"]["ok"] is True

def test_web_model_switch_persists_operator_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "model": {
                    "default_backend": "simple",
                    "deepseek": {"model_name": "deepseek-v4-flash", "thinking": "disabled"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESSLAB_CONFIG", str(config_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    runtime.operator_config = load_operator_config(config_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"

    _post(
        f"{base}/api/model",
        {"model_id": "deepseek-v4-pro", "backend": "deepseek", "effort": "max"},
    )

    reloaded = load_operator_config(config_path)
    assert reloaded.model_backend == "deepseek"
    assert reloaded.deepseek_model_name == "deepseek-v4-pro"
    assert reloaded.deepseek_reasoning_effort == "max"


def test_web_composer_commands_lists_skills(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("# Research skill", encoding="utf-8")
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    payload = _get(f"{base}/api/composer/commands")
    names = {item["name"] for item in payload["commands"]}
    assert "remember" in names
    assert payload["skills"][0]["name"] == "research"


def test_web_static_index_served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ts_static = tmp_path / "ts_static"
    assets = ts_static / "assets"
    assets.mkdir(parents=True)
    (ts_static / "index.html").write_text(
        '<!doctype html><html><body><div id="root">HarnessLab</div>'
        '<script type="module" src="/assets/index.js"></script></body></html>',
        encoding="utf-8",
    )
    (assets / "index.js").write_text("console.log('ts ui')", encoding="utf-8")
    monkeypatch.setattr(web_server, "_TS_STATIC_DIR", ts_static)

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    body = _open_url(f"{base}/").decode("utf-8")
    assert "HarnessLab" in body
    assert 'id="root"' in body
    assert "/assets/index.js" in body


def test_web_can_switch_to_ts_static_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ts_static = tmp_path / "ts_static"
    assets = ts_static / "assets"
    assets.mkdir(parents=True)
    (ts_static / "index.html").write_text(
        (
            "<!doctype html><html><body>"
            '<script type="module" src="/assets/index.js"></script>'
            "</body></html>"
        ),
        encoding="utf-8",
    )
    (assets / "index.js").write_text("console.log('ts ui')", encoding="utf-8")
    monkeypatch.setattr(web_server, "_TS_STATIC_DIR", ts_static)
    monkeypatch.setenv("HARNESSLAB_WEB_UI_VERSION", "ts")

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    body = _open_url(f"{base}/").decode("utf-8")
    assert "/assets/index.js" in body
    asset = _open_url(f"{base}/assets/index.js").decode("utf-8")
    assert "ts ui" in asset


def test_web_skills_list_api(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("# Research\n\nSearch deeply.", encoding="utf-8")
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    payload = _get(f"{base}/api/skills")
    names = {item["name"] for item in payload["skills"]}
    assert "research" in names
    assert "compact" in names
    compact = next(item for item in payload["skills"] if item["name"] == "compact")
    assert compact["scope"] == "catalog"
    assert compact["catalog_id"] == "compact"


def test_web_skills_preview_and_install_catalog(tmp_path: Path) -> None:
    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    preview = _get(f"{base}/api/skills/preview?catalog_id=compact")
    assert "/compact" in preview["markdown"]

    installed = _post(
        f"{base}/api/skills/install",
        {"catalog_id": "compact", "scope": "workspace"},
    )
    assert installed["ok"] is True
    assert (tmp_path / "skills" / "compact.md").is_file()


def test_web_patch_multi_agent_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"version": 1, "loop": {"multi_agent": {"enabled": false}}}\n')
    monkeypatch.setenv("HARNESSLAB_CONFIG", str(config_path))

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    payload = _post(f"{base}/api/settings/multi-agent", {"enabled": True})
    assert payload["multi_agent_enabled"] is True
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["loop"]["multi_agent"]["enabled"] is True


def test_web_patch_failover_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"version": 1, "model": {"default_backend": "simple", "failover_enabled": false}}\n'
    )
    monkeypatch.setenv("HARNESSLAB_CONFIG", str(config_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    port = _free_port()
    runtime = _web_runtime(tmp_path)
    _start_server(runtime, port)
    base = f"http://127.0.0.1:{port}"
    payload = _post(
        f"{base}/api/settings/failover",
        {"enabled": True, "fallbacks": ["deepseek"]},
    )
    assert payload["model_failover_enabled"] is True
    assert payload["model_fallbacks"] == ["deepseek"]
    assert "simple" in payload["model_failover_chain"]
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["model"]["failover_enabled"] is True
    assert saved["model"]["fallbacks"] == ["deepseek"]
