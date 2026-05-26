"""Tests for catalog-aligned runtime context limits."""

from __future__ import annotations

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.operator_config import OperatorConfig
from harnesslab.providers.context_limits import (
    align_runtime_limits_with_model,
    format_context_window,
)


def test_align_runtime_limits_deepseek_uses_1m_window() -> None:
    limits = RuntimeLimits()
    aligned = align_runtime_limits_with_model(
        limits,
        backend="deepseek",
        config=OperatorConfig(deepseek_model_name="deepseek-v4-flash"),
    )
    assert aligned.context_window_tokens == 1_048_576
    assert aligned.compaction_threshold_tokens == int(1_048_576 * 0.85)


def test_align_runtime_limits_gpt5_mini_uses_128k() -> None:
    limits = RuntimeLimits()
    aligned = align_runtime_limits_with_model(
        limits,
        backend="openai",
        config=OperatorConfig(openai_model_name="gpt-5-mini"),
    )
    assert aligned.context_window_tokens == 128_000


def test_format_context_window_labels() -> None:
    assert format_context_window(1_048_576) == "1M"
    assert format_context_window(200_000) == "200K"
    assert format_context_window(128_000) == "128K"
