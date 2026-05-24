"""Unit tests for session memory key formatting and note helpers."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.memory_policy import (
    append_note,
    format_memory_message,
    format_remember_global_note,
    format_remember_note,
    format_workspace_memory_message,
    parse_remember_command,
    parse_remember_global_command,
    session_memory_key,
    workspace_memory_key,
)


def test_session_memory_key_is_namespaced() -> None:
    assert session_memory_key("ses_abc") == "session:ses_abc:notes"


def test_parse_remember_command() -> None:
    assert parse_remember_command("/remember api json") == "api json"
    assert parse_remember_command("  /remember  hi  ") == "hi"
    assert parse_remember_command("/remember") is None
    assert parse_remember_command("/remember-global x") is None
    assert parse_remember_command("hello") is None


def test_parse_remember_global_command() -> None:
    assert parse_remember_global_command("/remember-global deploy Fridays") == (
        "deploy Fridays"
    )
    assert parse_remember_global_command("/remember-global") is None
    assert parse_remember_global_command("/remember x") is None


def test_workspace_memory_key_is_stable(tmp_path: Path) -> None:
    key_a = workspace_memory_key(tmp_path)
    key_b = workspace_memory_key(tmp_path.resolve())
    assert key_a == key_b
    assert key_a.startswith("workspace:")


def test_format_workspace_memory_message() -> None:
    text = format_workspace_memory_message("line one")
    assert "Workspace memory" in text
    assert "line one" in text


def test_format_remember_global_note() -> None:
    assert format_remember_global_note("deploy") == "[remember-global] 'deploy'"


def test_format_remember_note() -> None:
    assert format_remember_note("api json") == "[remember] 'api json'"


def test_append_note_joins_lines() -> None:
    assert append_note(None, "a") == "a"
    assert append_note("a", "b") == "a\nb"


def test_format_memory_message_includes_header() -> None:
    text = format_memory_message("line one")
    assert "Session memory" in text
    assert "line one" in text
