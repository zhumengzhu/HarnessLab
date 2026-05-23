"""Unit tests for session memory key formatting and note helpers."""

from __future__ import annotations

from harnesslab.core.memory_policy import (
    append_note,
    format_memory_message,
    format_remember_note,
    parse_remember_command,
    session_memory_key,
)


def test_session_memory_key_is_namespaced() -> None:
    assert session_memory_key("ses_abc") == "session:ses_abc:notes"


def test_parse_remember_command() -> None:
    assert parse_remember_command("/remember api json") == "api json"
    assert parse_remember_command("  /remember  hi  ") == "hi"
    assert parse_remember_command("/remember") is None
    assert parse_remember_command("hello") is None


def test_format_remember_note() -> None:
    assert format_remember_note("api json") == "[remember] 'api json'"


def test_append_note_joins_lines() -> None:
    assert append_note(None, "a") == "a"
    assert append_note("a", "b") == "a\nb"


def test_format_memory_message_includes_header() -> None:
    text = format_memory_message("line one")
    assert "Session memory" in text
    assert "line one" in text
