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


def test_tool_path_appends_assistant_tool_calls_and_tool_message(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="single message")
    loop.run_turn(session.id, '/tool write_file {"path":"b.txt","content":"x"}')

    tool_messages = [m for m in session.messages if m.role == "tool"]
    assistant_messages = [m for m in session.messages if m.role == "assistant"]
    assert len(tool_messages) == 1
    assert len(assistant_messages) == 1
    assert assistant_messages[0].tool_calls is not None
    assert assistant_messages[0].tool_calls[0]["id"] == tool_messages[0].tool_call_id
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


def test_invalid_args_writes_assistant_tool_calls_and_tool_message(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="schema msg")
    loop.run_turn(session.id, '/tool write_file {"path":123}')

    tool_messages = [m for m in session.messages if m.role == "tool"]
    assistant_messages = [m for m in session.messages if m.role == "assistant"]
    assert len(tool_messages) == 1
    assert len(assistant_messages) == 1
    assert assistant_messages[0].tool_calls is not None
    assert "Tool args invalid" in tool_messages[0].content
    assert tool_messages[0].tool_call_id is not None


# ----- Step 5 prerequisites: replay-ready trace shape -----


def test_user_input_event_is_recorded_before_decision(tmp_path: Path) -> None:
    """The replayer needs to know what the user fed each turn; the
    user_input_received event must always precede decision_made within
    that turn."""
    loop = build_runtime(tmp_path)
    session = loop.start(goal="trace shape")
    loop.run_turn(session.id, "hello")
    loop.run_turn(session.id, '/tool read_file {"path":"a.txt"}')

    events = _read_trace(tmp_path)
    user_inputs = [e for e in events if e["event_type"] == "user_input_received"]
    model_calls = [e for e in events if e["event_type"] == "model_call"]
    decisions = [e for e in events if e["event_type"] == "decision_made"]
    assert len(user_inputs) == 2
    assert len(model_calls) == 2
    assert len(decisions) == 2

    assert user_inputs[0]["payload"] == {"turn_index": 0, "user_input": "hello"}
    assert user_inputs[1]["payload"] == {
        "turn_index": 1,
        "user_input": '/tool read_file {"path":"a.txt"}',
    }

    keep = {
        "user_input_received",
        "step_started",
        "model_call",
        "decision_made",
        "step_completed",
        "session_finished",
    }
    types_in_order = [e["event_type"] for e in events if e["event_type"] in keep]
    one_turn = [
        "user_input_received",
        "step_started",
        "model_call",
        "decision_made",
        "step_completed",
        "session_finished",
    ]
    assert types_in_order == one_turn + one_turn


def test_decision_made_payload_is_replay_complete(tmp_path: Path) -> None:
    """decision_made must carry everything needed to rebuild a Decision."""
    loop = build_runtime(tmp_path)
    session = loop.start(goal="decision shape")
    loop.run_turn(session.id, "hi")
    loop.run_turn(session.id, '/tool write_file {"path":"x.txt","content":"y"}')

    events = _read_trace(tmp_path)
    decisions = [e for e in events if e["event_type"] == "decision_made"]
    assert decisions[0]["payload"]["kind"] == "final"
    assert decisions[0]["payload"]["tool_name"] is None
    assert decisions[0]["payload"]["tool_args"] == {}
    assert "HarnessLab is ready" in decisions[0]["payload"]["assistant_message"]
    assert decisions[1]["payload"] == {
        "kind": "tool",
        "tool_name": "write_file",
        "tool_args": {"path": "x.txt", "content": "y"},
        "assistant_message": None,
    }


def test_model_call_event_contains_latency_and_kind(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="model call event")
    loop.run_turn(session.id, "hello")

    events = _read_trace(tmp_path)
    model_calls = [e for e in events if e["event_type"] == "model_call"]
    assert len(model_calls) == 1
    payload = model_calls[0]["payload"]
    assert payload["model_name"] == "SimpleModel"
    assert payload["decision_kind"] == "final"
    assert payload["latency_ms"] >= 0


# ----- Phase 2.1 prerequisites: step + session_finished trace events -----


def test_step_started_and_completed_bracket_each_decision(tmp_path: Path) -> None:
    """Every model.decide call is wrapped by step_started/step_completed."""
    loop = build_runtime(tmp_path)
    session = loop.start(goal="step events")
    loop.run_turn(session.id, "hello")

    events = _read_trace(tmp_path)
    starts = [e for e in events if e["event_type"] == "step_started"]
    completes = [e for e in events if e["event_type"] == "step_completed"]
    assert len(starts) == 1
    assert len(completes) == 1
    assert starts[0]["payload"] == {"step_index": 0, "reason": "initial"}
    assert completes[0]["payload"] == {"step_index": 0, "outcome": "final"}


def test_session_finished_records_reason_and_step_count(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="finish event")
    loop.run_turn(session.id, "hi")
    loop.run_turn(session.id, '/tool write_file {"path":"a.txt","content":"x"}')

    events = _read_trace(tmp_path)
    finished = [e for e in events if e["event_type"] == "session_finished"]
    assert len(finished) == 2
    assert finished[0]["payload"] == {"reason": "final", "steps": 1}
    assert finished[1]["payload"] == {"reason": "max_steps", "steps": 1}


def test_step_completed_outcome_for_tool_path(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="tool outcome")
    loop.run_turn(session.id, '/tool write_file {"path":"a.txt","content":"x"}')

    events = _read_trace(tmp_path)
    completes = [e for e in events if e["event_type"] == "step_completed"]
    assert len(completes) == 1
    assert completes[0]["payload"] == {"step_index": 0, "outcome": "tool_ok"}


def test_step_completed_outcome_for_policy_denial(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="denial outcome")
    loop.run_turn(session.id, '/tool read_file {"path":"../../etc/passwd"}')

    events = _read_trace(tmp_path)
    completes = [e for e in events if e["event_type"] == "step_completed"]
    assert completes[-1]["payload"]["outcome"] == "tool_denied"


def test_step_completed_outcome_for_invalid_args(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="invalid args outcome")
    loop.run_turn(session.id, '/tool write_file {}')

    events = _read_trace(tmp_path)
    completes = [e for e in events if e["event_type"] == "step_completed"]
    assert completes[-1]["payload"]["outcome"] == "tool_invalid_args"
