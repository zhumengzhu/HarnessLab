"""Pure helpers for the TUI session sidebar and status bar.

Kept free of Textual imports so they can be unit-tested in isolation
(mirrors the ``span_feed`` / ``settings_actions`` split).
"""

from __future__ import annotations

from collections.abc import Iterable

from harnesslab.core.models import Session

DEFAULT_INPUT_PLACEHOLDER = "Message · /compact · /help"
AWAITING_INPUT_PLACEHOLDER = "Your reply · the agent is waiting…"


def awaiting_user_hint(status: str) -> str | None:
    """Affordance line for a turn that ended in ``ask_user`` / step budget.

    Returns ``None`` when no special prompt is warranted so the composer
    falls back to its default placeholder.
    """

    if status == "waiting_user":
        return "⏳ the agent is waiting for your reply"
    return None


def input_placeholder_for(status: str) -> str:
    """Composer placeholder reflecting whether the agent awaits an answer."""

    if awaiting_user_hint(status) is not None:
        return AWAITING_INPUT_PLACEHOLDER
    return DEFAULT_INPUT_PLACEHOLDER


def session_label(session: Session) -> str:
    """Short sidebar label: truncated title + turn count."""

    title = (session.title or session.goal or "session").strip()
    if len(title) > 22:
        title = f"{title[:19]}…"
    return f"{title} · t{session.turn_count}"


def filter_sessions(sessions: Iterable[Session], query: str) -> list[Session]:
    """Case-insensitive substring filter over title / goal / id.

    An empty (or whitespace-only) query returns all sessions unchanged so
    callers can use ``/find`` with no argument to clear an active filter.
    """

    needle = query.strip().lower()
    sessions = list(sessions)
    if not needle:
        return sessions
    matched: list[Session] = []
    for session in sessions:
        haystack = " ".join(
            part for part in (session.title, session.goal, session.id) if part
        ).lower()
        if needle in haystack:
            matched.append(session)
    return matched


def format_status_line(
    session: Session,
    *,
    backend: str,
    failover_enabled: bool,
    max_steps: int,
    session_filter: str = "",
) -> str:
    """One-line status bar summary including cumulative budget usage."""

    failover = "on" if failover_enabled else "off"
    usage = session.budget_usage
    parts = [
        f"session {session.id[:12]}…",
        f"model={backend}",
        f"failover={failover}",
        f"turns={session.turn_count}",
        f"steps={session.step_count}",
        f"max_steps={max_steps}",
        f"cost=${usage.cost_usd_total:.4f}",
    ]
    if usage.last_budget_status != "ok":
        parts.append(f"budget={usage.last_budget_status}")
    if session_filter.strip():
        parts.append(f"filter={session_filter.strip()!r}")
    return " · ".join(parts)
