"""Tests for session cost budget (Phase 5.10)."""

from __future__ import annotations

from harnesslab.core.budget import BudgetLimits, TurnBudgetUsage, detect_budget_breaches
from harnesslab.core.models import BudgetUsage


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
