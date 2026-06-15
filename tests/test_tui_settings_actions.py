"""Tests for TUI settings slash-command helpers."""

from __future__ import annotations

from harnesslab.tui.settings_actions import parse_slash_command


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
