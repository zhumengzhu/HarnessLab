"""Tests for TUI session-sidebar / status-bar pure helpers."""

from __future__ import annotations

from harnesslab.core.models import BudgetUsage, Session
from harnesslab.tui.session_list import (
    AWAITING_INPUT_PLACEHOLDER,
    DEFAULT_INPUT_PLACEHOLDER,
    awaiting_user_hint,
    filter_sessions,
    format_status_line,
    input_placeholder_for,
    session_label,
)
from harnesslab.tui.settings_actions import parse_slash_command


def _session(**kwargs) -> Session:
    return Session(goal=kwargs.pop("goal", "demo"), **kwargs)


def test_session_label_uses_title_and_truncates() -> None:
    s = _session(id="ses_1", title="A very long descriptive session title", turn_count=3)
    label = session_label(s)
    assert label.endswith("· t3")
    assert "…" in label
    assert len(label) <= 30


def test_session_label_falls_back_to_goal() -> None:
    s = _session(id="ses_2", goal="fix the bug", title=None, turn_count=0)
    assert session_label(s) == "fix the bug · t0"


def test_filter_sessions_empty_query_returns_all() -> None:
    sessions = [_session(id="a", goal="alpha"), _session(id="b", goal="beta")]
    assert filter_sessions(sessions, "") == sessions
    assert filter_sessions(sessions, "   ") == sessions


def test_filter_sessions_matches_title_goal_and_id() -> None:
    a = _session(id="ses_alpha", goal="write docs", title="Docs work")
    b = _session(id="ses_beta", goal="fix parser", title="Parser fix")
    sessions = [a, b]
    assert filter_sessions(sessions, "docs") == [a]
    assert filter_sessions(sessions, "parser") == [b]
    assert filter_sessions(sessions, "ses_beta") == [b]
    assert filter_sessions(sessions, "ZZZ") == []


def test_filter_sessions_is_case_insensitive() -> None:
    a = _session(id="x", goal="Refactor Loop")
    assert filter_sessions([a], "refactor loop") == [a]


def test_format_status_line_includes_cost_and_core_fields() -> None:
    s = _session(
        id="ses_abcdefabcdef123",
        turn_count=2,
        step_count=5,
        budget_usage=BudgetUsage(cost_usd_total=0.1234),
    )
    line = format_status_line(
        s, backend="deepseek", failover_enabled=True, max_steps=12
    )
    assert "model=deepseek" in line
    assert "failover=on" in line
    assert "turns=2" in line
    assert "steps=5" in line
    assert "max_steps=12" in line
    assert "cost=$0.1234" in line
    assert "budget=" not in line  # ok status is omitted


def test_format_status_line_surfaces_budget_breach_and_filter() -> None:
    s = _session(
        id="ses_1",
        budget_usage=BudgetUsage(last_budget_status="hard_exceeded"),
    )
    line = format_status_line(
        s,
        backend="simple",
        failover_enabled=False,
        max_steps=8,
        session_filter="docs",
    )
    assert "failover=off" in line
    assert "budget=hard_exceeded" in line
    assert "filter='docs'" in line


def test_awaiting_user_hint_only_for_waiting_user() -> None:
    assert awaiting_user_hint("waiting_user") is not None
    assert awaiting_user_hint("running") is None
    assert awaiting_user_hint("done") is None


def test_input_placeholder_switches_on_waiting_user() -> None:
    assert input_placeholder_for("waiting_user") == AWAITING_INPUT_PLACEHOLDER
    assert input_placeholder_for("running") == DEFAULT_INPUT_PLACEHOLDER
    assert input_placeholder_for("done") == DEFAULT_INPUT_PLACEHOLDER


def test_parse_slash_find_returns_query_tokens() -> None:
    assert parse_slash_command("/find docs") == ("/find", ["docs"])
    assert parse_slash_command("/find multi word query") == (
        "/find",
        ["multi", "word", "query"],
    )
    assert parse_slash_command("/find") == ("/find", [])
