"""Tests for TUI chat history search helper."""

from __future__ import annotations

from harnesslab.core.models import Message
from harnesslab.tui.history import search_messages


def _msg(role: str, content: str) -> Message:
    return Message(role=role, content=content)  # type: ignore[arg-type]


def test_search_empty_query_returns_nothing() -> None:
    messages = [_msg("user", "hello world")]
    assert search_messages(messages, "") == []
    assert search_messages(messages, "   ") == []


def test_search_matches_are_case_insensitive_with_index_and_role() -> None:
    messages = [
        _msg("user", "Please refactor the LOOP module"),
        _msg("assistant", "Done — the loop is cleaner now"),
        _msg("tool", "grep: nothing relevant"),
    ]
    hits = search_messages(messages, "loop")
    assert [h.index for h in hits] == [0, 1]
    assert hits[0].role == "user"
    assert "LOOP" in hits[0].snippet


def test_search_snippet_truncates_with_ellipsis() -> None:
    long = "x" * 100 + "needle" + "y" * 100
    hits = search_messages([_msg("assistant", long)], "needle", context=10)
    assert len(hits) == 1
    snippet = hits[0].snippet
    assert "needle" in snippet
    assert snippet.startswith("…")
    assert snippet.endswith("…")
    assert len(snippet) < len(long)


def test_search_respects_max_hits() -> None:
    messages = [_msg("user", f"match {i}") for i in range(30)]
    hits = search_messages(messages, "match", max_hits=5)
    assert len(hits) == 5
