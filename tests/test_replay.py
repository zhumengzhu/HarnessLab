"""Tests for the Step-5 replay stubs."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, Session, TraceEvent
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.file_tools import WriteFileTool
from harnesslab.tools.registry import ToolRegistry


def test_replay_model_returns_decisions_in_order() -> None:
    decisions = [
        Decision(kind="assistant", assistant_message="hi"),
        Decision(kind="tool", tool_name="write_file", tool_args={"path": "a.txt"}),
    ]
    model = ReplayModel(decisions=decisions)
    session = Session(goal="probe")

    first = model.decide(session, "hello")
    assert first.kind == "assistant"
    assert first.assistant_message == "hi"

    second = model.decide(session, "next")
    assert second.kind == "tool"
    assert second.tool_name == "write_file"

    assert model.remaining == 0


def test_replay_model_falls_back_when_exhausted() -> None:
    model = ReplayModel(decisions=[])
    decision = model.decide(Session(goal="x"), "anything")
    assert decision.kind == "assistant"
    assert decision.assistant_message is not None
    assert "exhausted" in decision.assistant_message


def test_replay_trace_recorder_collects_events_in_order() -> None:
    recorder = ReplayTraceRecorder()
    e1 = TraceEvent(run_id="r", session_id="s", event_type="a")
    e2 = TraceEvent(run_id="r", session_id="s", event_type="b")
    recorder.record(e1)
    recorder.record(e2)
    assert recorder.events == [e1, e2]
    assert recorder.event_types() == ["a", "b"]


def test_loop_drives_with_replay_components(tmp_path: Path) -> None:
    """ReplayModel + ReplayTraceRecorder are real Port implementations:
    the loop should drive them end-to-end without modification."""

    decisions = [
        Decision(
            kind="tool",
            tool_name="write_file",
            tool_args={"path": "out.txt", "content": "hi"},
        ),
        Decision(kind="assistant", assistant_message="all done"),
    ]
    model = ReplayModel(decisions=decisions)
    recorder = ReplayTraceRecorder()
    tools = ToolRegistry()
    tools.register(WriteFileTool(tmp_path))

    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
    )

    session = loop.start(goal="replay")
    tool_reply = loop.run_turn(session.id, "write something")
    assistant_reply = loop.run_turn(session.id, "wrap up")

    assert "[tool:write_file]" in tool_reply
    assert assistant_reply == "all done"
    assert "session_started" in recorder.event_types()
    assert "tool_executed" in recorder.event_types()
    assert model.remaining == 0
