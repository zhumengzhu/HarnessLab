"""Tests for the multi-step autonomous loop introduced in Phase 2.1.

`run_session` keeps calling the model — feeding tool results back via
``session.messages`` — until the model returns ``final`` / ``ask_user``
or ``max_steps`` is exhausted. ``run_turn`` is preserved as a
``max_steps=1`` wrapper so the original single-step contract still
holds (and is exercised by the existing eval/replay suites).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from span_assertions import (
    last_turn,
    llm_spans,
    read_spans_jsonl,
    span_events,
    step_spans,
    tool_spans,
    turn_terminal,
)

from harnesslab.cli import build_runtime
from harnesslab.core.budget import BudgetLimits
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision
from harnesslab.core.replay import ReplayModel, ReplaySpanRecorder
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.span_attributes import (
    HARNESSLAB_STEP_INDEX,
    HARNESSLAB_STEP_REASON,
)
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.shell_tool import RunShellSafeTool


def _build_loop(
    tmp_path: Path,
    decisions: list[Decision],
    *,
    replan_after_steps: int | None = None,
    budget_limits: BudgetLimits | None = None,
) -> tuple[HarnessLoop, ReplaySpanRecorder]:
    limits = RuntimeLimits()
    tools = ToolRegistry()
    tools.register(ReadFileTool(tmp_path, limits=limits))
    tools.register(WriteFileTool(tmp_path, limits=limits))
    tools.register(RunShellSafeTool(tmp_path, limits=limits))
    recorder = ReplaySpanRecorder()
    loop = HarnessLoop(
        model=ReplayModel(decisions=decisions),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
        replan_after_steps=replan_after_steps,
        budget_limits=budget_limits,
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
    spans = recorder.spans
    assert len(tool_spans(spans)) == 1
    assert len(llm_spans(spans)) == 2
    reason, steps = turn_terminal(last_turn(spans))
    assert reason == "final"
    assert steps == 2


def test_run_session_terminates_on_ask_user(tmp_path: Path) -> None:
    decisions = [Decision(kind="ask_user", assistant_message="What next?")]
    loop, recorder = _build_loop(tmp_path, decisions)
    session = loop.start(goal="ask")
    response = loop.run_session(session.id, "start")

    assert response == "What next?"
    reason, steps = turn_terminal(last_turn(recorder.spans))
    assert reason == "ask_user"
    assert steps == 1


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

    assert len(step_spans(recorder.spans)) == 3
    reason, steps = turn_terminal(last_turn(recorder.spans))
    assert reason == "max_steps"
    assert steps == 3


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

    steps = step_spans(recorder.spans)
    assert steps[0].attributes[HARNESSLAB_STEP_INDEX] == 0
    assert steps[0].attributes[HARNESSLAB_STEP_REASON] == "initial"
    assert steps[1].attributes[HARNESSLAB_STEP_INDEX] == 1
    assert steps[1].attributes[HARNESSLAB_STEP_REASON] == "after_tool_ok"


def test_run_session_rejects_zero_max_steps(tmp_path: Path) -> None:
    loop, _ = _build_loop(tmp_path, [])
    session = loop.start(goal="bad")
    with pytest.raises(ValueError):
        loop.run_session(session.id, "go", max_steps=0)


def test_run_session_plan_decision_emits_plan_trace(tmp_path: Path) -> None:
    decisions = [
        Decision(kind="plan", assistant_message="1) inspect 2) patch 3) verify"),
        Decision(kind="final", assistant_message="done"),
    ]
    loop, recorder = _build_loop(tmp_path, decisions)
    session = loop.start(goal="plan mode")
    response = loop.run_session(session.id, "fix issue", max_steps=4)
    assert response == "done"

    plan_events = span_events(recorder.spans, "plan.emitted")
    assert len(plan_events) == 1
    assert "inspect" in str(plan_events[0][1].get("plan"))


def test_run_session_emits_replan_reminder_after_interval(tmp_path: Path) -> None:
    decisions = [
        Decision(kind="assistant", assistant_message="step 1"),
        Decision(kind="assistant", assistant_message="step 2"),
        Decision(kind="final", assistant_message="done"),
    ]
    loop, recorder = _build_loop(tmp_path, decisions, replan_after_steps=2)
    session = loop.start(goal="long run")
    loop.run_session(session.id, "go", max_steps=4)
    reminders = span_events(recorder.spans, "plan.recheck_requested")
    assert len(reminders) == 1
    assert reminders[0][1]["steps_used"] == 2


def test_run_turn_is_single_step_wrapper(tmp_path: Path) -> None:
    """run_turn must remain a max_steps=1 wrapper."""
    loop = build_runtime(tmp_path)
    session = loop.start(goal="turn shape")
    loop.run_turn(session.id, '/tool write_file {"path":"a.txt","content":"x"}')

    raw = read_spans_jsonl(tmp_path)
    turns = [row for row in raw if row.get("name") == "harnesslab.turn"]
    assert len(turns) == 1
    assert turns[0]["attributes"]["harnesslab.terminal.reason"] == "max_steps"
    assert turns[0]["attributes"]["harnesslab.steps.used"] == 1
    llm_rows = [row for row in raw if row.get("name") == "llm.generate"]
    assert len(llm_rows) == 1


def test_cli_run_default_max_steps_drives_full_loop(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="cli style")
    response = loop.run_session(session.id, "/final all done")
    assert response == "all done"

    raw = read_spans_jsonl(tmp_path)
    turns = [row for row in raw if row.get("name") == "harnesslab.turn"]
    assert turns[-1]["attributes"]["harnesslab.terminal.reason"] == "final"


def test_budget_hard_limit_stops_turn_with_ask_user(tmp_path: Path) -> None:
    decisions = [
        Decision(kind="assistant", assistant_message="step one"),
        Decision(kind="assistant", assistant_message="step two"),
    ]
    loop, recorder = _build_loop(
        tmp_path,
        decisions,
        budget_limits=BudgetLimits(
            enabled=True,
            action_on_hard="ask_user",
            max_llm_calls_per_turn=1,
        ),
    )
    session = loop.start(goal="budget guard")
    response = loop.run_session(session.id, "go", max_steps=4)
    assert "Budget hard limit exceeded" in response
    reason, _ = turn_terminal(last_turn(recorder.spans))
    assert reason == "ask_user"
    assert span_events(recorder.spans, "budget.hard_exceeded")


def test_budget_soft_threshold_emits_warning_event(tmp_path: Path) -> None:
    decisions = [
        Decision(
            kind="tool",
            tool_name="write_file",
            tool_args={"path": "a.txt", "content": "x"},
        ),
        Decision(kind="final", assistant_message="done"),
    ]
    loop, recorder = _build_loop(
        tmp_path,
        decisions,
        budget_limits=BudgetLimits(
            enabled=True,
            soft_ratio=0.5,
            max_tool_calls_per_turn=2,
        ),
    )
    session = loop.start(goal="soft budget")
    loop.run_session(session.id, "do it", max_steps=3)
    soft = span_events(recorder.spans, "budget.soft_threshold")
    assert soft
    assert soft[0][1]["dimension"] == "max_tool_calls_per_turn"
