"""Tests for the Step-5 replay stubs."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, Session
from harnesslab.core.replay import ReplayModel, ReplaySpanRecorder
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


def test_replay_span_recorder_collects_spans_in_order() -> None:
    recorder = ReplaySpanRecorder()
    h1 = recorder.start_span(
        "harnesslab.turn",
        session_id="s",
        trace_id="t" * 32,
        turn_index=0,
    )
    h2 = recorder.start_span(
        "harnesslab.step",
        session_id="s",
        parent=h1,
    )
    r2 = recorder.end_span(h2)
    r1 = recorder.end_span(h1)
    assert recorder.spans == [r2, r1]
    assert [s.name for s in recorder.spans] == ["harnesslab.step", "harnesslab.turn"]


def test_loop_drives_with_replay_components(tmp_path: Path) -> None:
    """ReplayModel + ReplaySpanRecorder are real Port implementations:
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
    recorder = ReplaySpanRecorder()
    tools = ToolRegistry()
    tools.register(WriteFileTool(tmp_path))

    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
    )

    session = loop.start(goal="replay")
    tool_reply = loop.run_turn(session.id, "write something")
    assistant_reply = loop.run_turn(session.id, "wrap up")

    assert "[tool:write_file]" in tool_reply
    assert assistant_reply == "all done"
    names = [s.name for s in recorder.spans]
    assert "harnesslab.turn" in names
    assert "tool.write_file" in names
    assert model.remaining == 0
