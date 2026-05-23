import json
from pathlib import Path

from harnesslab.cli import build_runtime


def _read_trace(workspace_root: Path) -> list[dict]:
    trace_path = workspace_root / ".harnesslab" / "trace.jsonl"
    return [json.loads(line) for line in trace_path.read_text().splitlines() if line]


def test_trace_records_full_tool_executed_payload(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="write")
    loop.run_turn(session.id, '/tool write_file {"path":"a.txt","content":"hi"}')

    events = _read_trace(tmp_path)
    executed = [e for e in events if e["event_type"] == "tool_executed"]
    assert len(executed) == 1
    payload = executed[0]["payload"]
    for key in (
        "tool_call_id",
        "tool",
        "args",
        "policy_decision",
        "started_at",
        "ended_at",
        "duration_ms",
        "ok",
        "output_size",
        "output_preview",
        "output_truncated",
    ):
        assert key in payload, f"missing trace field: {key}"
    assert payload["tool"] == "write_file"
    assert payload["ok"] is True
    assert payload["policy_decision"].startswith("allow:")
    assert payload["started_at"] is not None
    assert payload["ended_at"] is not None
    assert payload["duration_ms"] is not None
    assert payload["duration_ms"] >= 0
    assert payload["output_size"] > 0


def test_trace_records_denied_with_policy_decision(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="bad")
    loop.run_turn(session.id, '/tool read_file {"path":"../../etc/passwd"}')

    events = _read_trace(tmp_path)
    denied = [e for e in events if e["event_type"] == "tool_denied"]
    assert len(denied) == 1
    payload = denied[0]["payload"]
    assert payload["tool"] == "read_file"
    assert payload["policy_decision"].startswith("deny:")
    assert "out of workspace" in payload["reason"]


def test_tool_path_appends_single_tool_message(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="single message")
    loop.run_turn(session.id, '/tool write_file {"path":"b.txt","content":"x"}')

    tool_messages = [m for m in session.messages if m.role == "tool"]
    assistant_messages = [m for m in session.messages if m.role == "assistant"]
    assert len(tool_messages) == 1
    assert len(assistant_messages) == 0
    assert tool_messages[0].tool_call_id is not None
    assert tool_messages[0].tool_call_id.startswith("tool_")


def test_invalid_args_short_circuit_before_policy(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="schema gate")
    reply = loop.run_turn(session.id, '/tool write_file {}')

    assert "Tool args invalid" in reply
    events = _read_trace(tmp_path)
    invalid = [e for e in events if e["event_type"] == "tool_invalid_args"]
    assert len(invalid) == 1
    payload = invalid[0]["payload"]
    assert payload["tool"] == "write_file"
    assert payload["args"] == {}
    assert "error" in payload and payload["error"]

    # The schema gate must run *before* policy: no tool_denied / tool_executed
    # event should be emitted for this turn.
    assert not any(e["event_type"] == "tool_denied" for e in events)
    assert not any(e["event_type"] == "tool_executed" for e in events)


def test_invalid_args_writes_only_one_tool_message(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="schema msg")
    loop.run_turn(session.id, '/tool write_file {"path":123}')

    tool_messages = [m for m in session.messages if m.role == "tool"]
    assistant_messages = [m for m in session.messages if m.role == "assistant"]
    assert len(tool_messages) == 1
    assert len(assistant_messages) == 0
    assert "Tool args invalid" in tool_messages[0].content
    assert tool_messages[0].tool_call_id is not None
