"""Tests for the multi-step autonomous loop introduced in Phase 2.1.

`run_session` keeps calling the model — feeding tool results back via
``session.messages`` — until the model returns ``final`` / ``ask_user``
or ``max_steps`` is exhausted. ``run_turn`` is preserved as a
``max_steps=1`` wrapper so the original single-step contract still
holds (and is exercised by the existing eval/replay suites).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesslab.cli import build_runtime
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.shell_tool import RunShellSafeTool


def _read_trace(workspace_root: Path) -> list[dict]:
    trace_path = workspace_root / ".harnesslab" / "trace.jsonl"
    return [json.loads(line) for line in trace_path.read_text().splitlines() if line]


def _build_loop(
    tmp_path: Path,
    decisions: list[Decision],
) -> tuple[HarnessLoop, ReplayTraceRecorder]:
    limits = RuntimeLimits()
    tools = ToolRegistry()
    tools.register(ReadFileTool(tmp_path, limits=limits))
    tools.register(WriteFileTool(tmp_path, limits=limits))
    tools.register(RunShellSafeTool(tmp_path, limits=limits))
    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel(decisions=decisions),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
    )
    return loop, recorder


def test_run_session_executes_tool_then_final(tmp_path: Path) -> None:
    """Classic agentic pattern: tool call, observe result, summarize."""
    decisions = [
        Decision(
            kind="tool",
            tool_name="write_file",
            tool_args={"path": "notes.txt", "content": "hi"},
        ),
        Decision(kind="final", assistant_message="Wrote the note."),
    ]
    loop, recorder = _build_loop(tmp_path, decisions)
    session = loop.start(goal="multi-step")
    response = loop.run_session(session.id, "please write hi to notes.txt")

    assert response == "Wrote the note."
    types = [e.event_type for e in recorder.events]
    assert types.count("tool_executed") == 1
    assert types.count("decision_made") == 2

    finished = [e for e in recorder.events if e.event_type == "session_finished"]
    assert len(finished) == 1
    assert finished[0].payload == {"reason": "final", "steps": 2}


def test_run_session_terminates_on_ask_user(tmp_path: Path) -> None:
    decisions = [Decision(kind="ask_user", assistant_message="What next?")]
    loop, recorder = _build_loop(tmp_path, decisions)
    session = loop.start(goal="ask")
    response = loop.run_session(session.id, "start")

    assert response == "What next?"
    finished = [e for e in recorder.events if e.event_type == "session_finished"]
    assert finished[0].payload == {"reason": "ask_user", "steps": 1}


def test_run_session_hits_max_steps(tmp_path: Path) -> None:
    """A model that never returns terminal must be stopped by max_steps."""
    decisions = [
        Decision(
            kind="tool",
            tool_name="write_file",
            tool_args={"path": f"f{i}.txt", "content": "x"},
        )
        for i in range(5)
    ]
    loop, recorder = _build_loop(tmp_path, decisions)
    session = loop.start(goal="runaway")
    loop.run_session(session.id, "go", max_steps=3)

    started = [e for e in recorder.events if e.event_type == "step_started"]
    assert len(started) == 3
    finished = [e for e in recorder.events if e.event_type == "session_finished"]
    assert finished[0].payload == {"reason": "max_steps", "steps": 3}


def test_run_session_step_started_reason_propagates_prev_outcome(tmp_path: Path) -> None:
    decisions = [
        Decision(
            kind="tool",
            tool_name="write_file",
            tool_args={"path": "a.txt", "content": "x"},
        ),
        Decision(kind="final", assistant_message="ok"),
    ]
    loop, recorder = _build_loop(tmp_path, decisions)
    session = loop.start(goal="reason")
    loop.run_session(session.id, "do it")

    started = [e for e in recorder.events if e.event_type == "step_started"]
    assert started[0].payload == {"step_index": 0, "reason": "initial"}
    assert started[1].payload == {"step_index": 1, "reason": "after_tool_ok"}


def test_run_session_rejects_zero_max_steps(tmp_path: Path) -> None:
    loop, _ = _build_loop(tmp_path, [])
    session = loop.start(goal="bad")
    with pytest.raises(ValueError):
        loop.run_session(session.id, "go", max_steps=0)


def test_run_turn_is_single_step_wrapper(tmp_path: Path) -> None:
    """run_turn must remain a max_steps=1 wrapper so the existing
    single-step trace contract (used by eval/replay) still holds."""
    loop = build_runtime(tmp_path)
    session = loop.start(goal="turn shape")
    loop.run_turn(session.id, '/tool write_file {"path":"a.txt","content":"x"}')

    events = _read_trace(tmp_path)
    decisions = [e for e in events if e["event_type"] == "decision_made"]
    assert len(decisions) == 1
    finished = [e for e in events if e["event_type"] == "session_finished"]
    assert finished[0]["payload"] == {"reason": "max_steps", "steps": 1}


def test_cli_run_default_max_steps_drives_full_loop(tmp_path: Path) -> None:
    """The CLI default (max_steps=DEFAULT_MAX_STEPS) lets a SimpleModel
    session terminate naturally on /final without max-step truncation."""
    loop = build_runtime(tmp_path)
    session = loop.start(goal="cli style")
    response = loop.run_session(session.id, "/final all done")
    assert response == "all done"

    events = _read_trace(tmp_path)
    finished = [e for e in events if e["event_type"] == "session_finished"]
    assert finished[0]["payload"]["reason"] == "final"
