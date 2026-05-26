"""Tests for DeepSeek thinking / reasoning_effort config helpers."""

from __future__ import annotations

import pytest

from harnesslab.providers.deepseek_config import (
    apply_deepseek_ui_effort,
    deepseek_ui_effort,
    parse_deepseek_thinking_fields,
)


def test_parse_disabled() -> None:
    assert parse_deepseek_thinking_fields(thinking_raw="disabled") == ("disabled", None)


def test_parse_high_shorthand() -> None:
    assert parse_deepseek_thinking_fields(thinking_raw="high") == ("enabled", "high")


def test_parse_max_shorthand() -> None:
    assert parse_deepseek_thinking_fields(thinking_raw="max") == ("enabled", "max")


def test_parse_enabled_with_reasoning_effort() -> None:
    assert parse_deepseek_thinking_fields(
        thinking_raw="enabled",
        reasoning_effort_raw="max",
    ) == ("enabled", "max")


def test_deepseek_ui_effort_roundtrip() -> None:
    assert deepseek_ui_effort(thinking_mode="disabled", reasoning_effort=None) == "disabled"
    assert deepseek_ui_effort(thinking_mode="enabled", reasoning_effort="high") == "high"
    assert deepseek_ui_effort(thinking_mode="enabled", reasoning_effort="max") == "max"


def test_apply_deepseek_ui_effort() -> None:
    assert apply_deepseek_ui_effort("disabled") == ("disabled", None)
    assert apply_deepseek_ui_effort("high") == ("enabled", "high")
    assert apply_deepseek_ui_effort("max") == ("enabled", "max")


def test_apply_deepseek_ui_effort_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported DeepSeek effort"):
        apply_deepseek_ui_effort("medium")
