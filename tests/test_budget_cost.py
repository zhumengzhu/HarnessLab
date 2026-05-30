"""Tests for session cost budget (Phase 5.10)."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.budget import BudgetLimits, TurnBudgetUsage, detect_budget_breaches
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import BudgetUsage, Decision
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.registry import ToolRegistry


def test_cost_budget_hard_breach() -> None:
    limits = BudgetLimits(enabled=True, max_session_cost_usd_total=1.0, soft_ratio=0.8)
    session = BudgetUsage(cost_usd_total=1.01)
    breaches = detect_budget_breaches(
        limits=limits,
        turn=TurnBudgetUsage(),
        session=session,
    )
    hard = [
        b
        for b in breaches
        if b.dimension == "max_session_cost_usd_total" and b.severity == "hard"
    ]
    assert hard


def _build_cost_loop(
    tmp_path: Path,
    *,
    decisions: list[Decision],
    call_meta: dict[str, object],
    budget_limits: BudgetLimits,
) -> tuple[HarnessLoop, ReplayTraceRecorder]:
    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel(decisions=decisions, call_meta=call_meta),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=ToolRegistry(),
        trace=recorder,
        budget_limits=budget_limits,
    )
    return loop, recorder


def test_cost_budget_hard_stop_in_loop(tmp_path: Path) -> None:
    call_meta = {
        "model_name": "deepseek-v4-flash",
        "request_tokens": 1000,
        "response_tokens": 1000,
    }
    loop, recorder = _build_cost_loop(
        tmp_path,
        decisions=[Decision(kind="final", assistant_message="should not reach")],
        call_meta=call_meta,
        budget_limits=BudgetLimits(
            enabled=True,
            action_on_hard="final",
            max_session_cost_usd_total=0.00001,
        ),
    )
    session = loop.start(goal="cost guard")
    response = loop.run_session(session.id, "expensive turn", max_steps=1)

    assert "Budget hard limit exceeded" in response
    assert session.budget_usage.cost_usd_total > 0.0
    hard = [
        e
        for e in recorder.events
        if e.event_type == "budget_hard_exceeded"
        and e.payload.get("dimension") == "max_session_cost_usd_total"
    ]
    assert hard


def test_cost_budget_soft_threshold_in_loop(tmp_path: Path) -> None:
    call_meta = {
        "model_name": "deepseek-v4-flash",
        "request_tokens": 1000,
        "response_tokens": 1000,
    }
    loop, recorder = _build_cost_loop(
        tmp_path,
        decisions=[Decision(kind="final", assistant_message="done")],
        call_meta=call_meta,
        budget_limits=BudgetLimits(
            enabled=True,
            soft_ratio=0.5,
            action_on_hard="final",
            max_session_cost_usd_total=0.00084,
        ),
    )
    session = loop.start(goal="soft cost guard")
    loop.run_session(session.id, "one call", max_steps=1)

    soft = [
        e
        for e in recorder.events
        if e.event_type == "budget_soft_threshold"
        and e.payload.get("dimension") == "max_session_cost_usd_total"
    ]
    assert soft
    assert session.budget_usage.last_budget_status == "soft_exceeded"
