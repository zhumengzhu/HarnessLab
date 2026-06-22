"""Tests for TUI settings slash-command helpers."""

from __future__ import annotations

from harnesslab.tui.settings_actions import (
    SLASH_COMMANDS,
    format_help,
    parse_slash_command,
    slash_suggestions,
)


def test_parse_slash_settings() -> None:
    assert parse_slash_command("/settings") == ("/settings", [])


def test_parse_slash_failover() -> None:
    assert parse_slash_command("/failover on") == ("/failover", ["on"])
    assert parse_slash_command("/failover off") == ("/failover", ["off"])


def test_parse_slash_model() -> None:
    assert parse_slash_command("/model simple") == ("/model", ["simple"])


def test_parse_slash_unknown_returns_none() -> None:
    assert parse_slash_command("/unknown arg") is None
    assert parse_slash_command("hello") is None


def test_parse_slash_copy() -> None:
    assert parse_slash_command("/copy") == ("/copy", [])


def test_slash_suggestions_cover_commands_and_variants() -> None:
    suggestions = slash_suggestions()
    commands = {command for command, _ in SLASH_COMMANDS}
    assert commands.issubset(set(suggestions))
    # bare commands precede argument variants so a short prefix completes
    # to the command itself
    assert suggestions.index("/model") < suggestions.index("/model deepseek")
    assert "/failover on" in suggestions
    assert all(s.startswith("/") for s in suggestions)


def test_format_help_lists_every_command() -> None:
    help_text = format_help()
    for command, _ in SLASH_COMMANDS:
        assert command in help_text
    assert "Esc=stop" in help_text
