"""Budget policy and runtime accounting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from harnesslab.core.models import BudgetUsage

BudgetAction = Literal["ask_user", "final", "error"]


@dataclass(frozen=True)
class BudgetLimits:
    enabled: bool = False
    soft_ratio: float = 0.8
    action_on_hard: BudgetAction = "ask_user"
    max_llm_calls_per_turn: int | None = None
    max_tool_calls_per_turn: int | None = None
    max_turn_wall_time_ms: int | None = None
    max_session_tokens_total: int | None = None
    max_session_tool_calls_total: int | None = None
    max_session_wall_time_ms_total: int | None = None


@dataclass
class TurnBudgetUsage:
    llm_calls: int = 0
    tool_calls: int = 0
    wall_time_ms: int = 0
    soft_notified: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class BudgetBreach:
    dimension: str
    current: float
    limit: float
    ratio: float
    scope: Literal["turn", "session"]
    severity: Literal["soft", "hard"]


def detect_budget_breaches(
    *,
    limits: BudgetLimits,
    turn: TurnBudgetUsage,
    session: BudgetUsage,
) -> list[BudgetBreach]:
    if not limits.enabled:
        return []
    checks: list[tuple[str, float, float | None, Literal["turn", "session"]]] = [
        (
            "max_llm_calls_per_turn",
            float(turn.llm_calls),
            _as_float(limits.max_llm_calls_per_turn),
            "turn",
        ),
        (
            "max_tool_calls_per_turn",
            float(turn.tool_calls),
            _as_float(limits.max_tool_calls_per_turn),
            "turn",
        ),
        (
            "max_turn_wall_time_ms",
            float(turn.wall_time_ms),
            _as_float(limits.max_turn_wall_time_ms),
            "turn",
        ),
        (
            "max_session_tokens_total",
            float(session.tokens_total),
            _as_float(limits.max_session_tokens_total),
            "session",
        ),
        (
            "max_session_tool_calls_total",
            float(session.tool_calls_total),
            _as_float(limits.max_session_tool_calls_total),
            "session",
        ),
        (
            "max_session_wall_time_ms_total",
            float(session.wall_time_ms_total),
            _as_float(limits.max_session_wall_time_ms_total),
            "session",
        ),
    ]
    out: list[BudgetBreach] = []
    for dim, current, limit, scope in checks:
        if limit is None or limit <= 0:
            continue
        ratio = current / limit if limit else 0.0
        if current > limit:
            out.append(
                BudgetBreach(
                    dimension=dim,
                    current=current,
                    limit=limit,
                    ratio=ratio,
                    scope=scope,
                    severity="hard",
                )
            )
            continue
        if ratio >= limits.soft_ratio:
            out.append(
                BudgetBreach(
                    dimension=dim,
                    current=current,
                    limit=limit,
                    ratio=ratio,
                    scope=scope,
                    severity="soft",
                )
            )
    return out


def _as_float(value: int | None) -> float | None:
    if value is None:
        return None
    return float(value)
