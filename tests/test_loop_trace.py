from pathlib import Path

from span_assertions import read_spans_jsonl

from harnesslab.cli import build_runtime
from harnesslab.core.operator_config import OperatorConfig
from harnesslab.telemetry.span_attributes import (
    HARNESSLAB_DECISION_KIND,
    HARNESSLAB_STEP_OUTCOME,
    HARNESSLAB_STEP_REASON,
    HARNESSLAB_USER_INPUT_PREVIEW,
)


def test_trace_records_full_tool_executed_payload(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="write")
    loop.run_turn(session.id, '/tool write_file {"path":"a.txt","content":"hi"}')

    tools = tool_spans_from_jsonl(tmp_path)
    assert len(tools) == 1
    span = tools[0]
    assert span["name"] == "tool.write_file"
    assert span["attributes"]["harnesslab.tool.ok"] is True
    assert span["attributes"]["harnesslab.policy.decision"].startswith("allow:")
    metrics = span["metrics"]
    assert metrics.get("duration_ms") is not None
    assert metrics.get("duration_ms") >= 0
    assert metrics.get("output_size", 0) > 0


def test_trace_records_denied_with_policy_decision(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="bad")
    loop.run_turn(session.id, '/tool read_file {"path":"../../etc/passwd"}')

    tools = tool_spans_from_jsonl(tmp_path)
    assert len(tools) == 1
    assert tools[0]["status"] == "error"
    events = tools[0].get("events") or []
    denied = [e for e in events if e["name"] == "tool.policy_denied"]
    assert denied
    assert "out of workspace" in str(denied[0]["attributes"].get("reason"))


def test_trace_records_hook_events_when_pre_tool_blocks(tmp_path: Path) -> None:
    loop = build_runtime(
        tmp_path,
        operator_config=OperatorConfig(
            pre_tool_hooks=(
                {
                    "name": "block-shell",
                    "type": "prompt",
                    "config": {
                        "tool_name_contains": "run_shell_safe",
                        "action": "block",
                        "reason": "blocked by pre hook",
                    },
                },
            )
        ),
    )
    session = loop.start(goal="hook trace")
    loop.run_turn(session.id, '/tool run_shell_safe {"command":"pwd"}')

    tools = tool_spans_from_jsonl(tmp_path)
    events = tools[0].get("events") or []
    blocked = [e for e in events if e["name"] == "tool.hook_blocked"]
    assert blocked
    assert any(
        e["attributes"].get("reason") == "blocked by pre hook" for e in blocked
    )


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
    tools = tool_spans_from_jsonl(tmp_path)
    events = tools[0].get("events") or []
    assert any(e["name"] == "tool.args_invalid" for e in events)
    assert tools[0]["status"] == "error"


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


def test_turn_attrs_capture_user_input_preview(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="trace shape")
    loop.run_turn(session.id, "hello")
    loop.run_turn(session.id, '/tool read_file {"path":"a.txt"}')

    turns = turn_spans_from_jsonl(tmp_path)
    assert len(turns) == 2
    assert turns[0]["attributes"][HARNESSLAB_USER_INPUT_PREVIEW]
    assert turns[1]["attributes"][HARNESSLAB_USER_INPUT_PREVIEW]


def test_llm_span_carries_decision_kind(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="decision shape")
    loop.run_turn(session.id, "hi")

    raw = read_spans_jsonl(tmp_path)
    llm = [row for row in raw if row.get("name") == "llm.generate"]
    assert llm[0]["attributes"][HARNESSLAB_DECISION_KIND] == "final"
    assert llm[0]["metrics"].get("latency_ms") is not None


def test_step_spans_bracket_each_decision(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="step events")
    loop.run_turn(session.id, "hello")

    steps = step_spans_from_jsonl(tmp_path)
    assert len(steps) == 1
    assert steps[0]["attributes"][HARNESSLAB_STEP_REASON] == "initial"
    assert steps[0]["attributes"][HARNESSLAB_STEP_OUTCOME] == "final"


def test_turn_terminal_reason_and_steps(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="finish event")
    loop.run_turn(session.id, "hi")
    loop.run_turn(session.id, '/tool write_file {"path":"a.txt","content":"x"}')

    turns = turn_spans_from_jsonl(tmp_path)
    assert turns[0]["attributes"]["harnesslab.terminal.reason"] == "final"
    assert turns[0]["attributes"]["harnesslab.steps.used"] == 1
    assert turns[1]["attributes"]["harnesslab.terminal.reason"] == "max_steps"
    assert turns[1]["attributes"]["harnesslab.steps.used"] == 1


def test_step_completed_outcome_for_tool_path(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="tool outcome")
    loop.run_turn(session.id, '/tool write_file {"path":"a.txt","content":"x"}')

    steps = step_spans_from_jsonl(tmp_path)
    assert steps[0]["attributes"][HARNESSLAB_STEP_OUTCOME] == "tool_ok"


def test_step_completed_outcome_for_policy_denial(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="denial outcome")
    loop.run_turn(session.id, '/tool read_file {"path":"../../etc/passwd"}')

    steps = step_spans_from_jsonl(tmp_path)
    assert steps[-1]["attributes"][HARNESSLAB_STEP_OUTCOME] == "tool_denied"


def test_step_completed_outcome_for_invalid_args(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="invalid args outcome")
    loop.run_turn(session.id, '/tool write_file {}')

    steps = step_spans_from_jsonl(tmp_path)
    assert steps[-1]["attributes"][HARNESSLAB_STEP_OUTCOME] == "tool_invalid_args"


def tool_spans_from_jsonl(workspace_root: Path) -> list[dict]:
    return [
        row
        for row in read_spans_jsonl(workspace_root)
        if str(row.get("name", "")).startswith("tool.")
        and not str(row.get("name", "")).startswith("tool.hooks.")
    ]


def turn_spans_from_jsonl(workspace_root: Path) -> list[dict]:
    return [row for row in read_spans_jsonl(workspace_root) if row.get("name") == "harnesslab.turn"]


def step_spans_from_jsonl(workspace_root: Path) -> list[dict]:
    return [row for row in read_spans_jsonl(workspace_root) if row.get("name") == "harnesslab.step"]
