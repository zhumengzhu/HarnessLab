"""Tests for Phase 4.1 provider registry."""

from __future__ import annotations

import pytest

from harnesslab.core.operator_config import OperatorConfig
from harnesslab.core.prompt import PromptComposer
from harnesslab.core.simple_model import SimpleModel
from harnesslab.providers.anthropic import AnthropicModel
from harnesslab.providers.deepseek import DEFAULT_MODEL, DeepSeekModel
from harnesslab.providers.openai_responses import OpenAIResponsesModel
from harnesslab.providers.registry import (
    create_model,
    model_label,
    normalize_backend,
)


def test_normalize_backend_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown model backend"):
        normalize_backend("openrouter")


def test_create_simple_model() -> None:
    model = create_model(
        "simple",
        config=None,
        tool_specs_provider=lambda: [],
        dynamic_blocks_provider=lambda _s: [],
    )
    assert isinstance(model, SimpleModel)


def test_create_deepseek_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        create_model(
            "deepseek",
            config=OperatorConfig(deepseek_model_name="deepseek-v4-pro"),
            tool_specs_provider=lambda: [],
            dynamic_blocks_provider=lambda _s: [],
        )


def test_create_deepseek_uses_config_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    model = create_model(
        "deepseek",
        config=OperatorConfig(
            deepseek_model_name="deepseek-v4-pro",
            deepseek_thinking="disabled",
        ),
        tool_specs_provider=lambda: [],
        dynamic_blocks_provider=lambda _s: [],
        composer=PromptComposer(),
    )
    assert isinstance(model, DeepSeekModel)
    assert model._model_name == "deepseek-v4-pro"
    assert model._thinking_mode == "disabled"


def test_create_anthropic_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        create_model(
            "anthropic",
            config=OperatorConfig(anthropic_model_name="claude-sonnet-4-6"),
            tool_specs_provider=lambda: [],
            dynamic_blocks_provider=lambda _s: [],
        )


def test_create_openai_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_model(
            "openai",
            config=OperatorConfig(openai_model_name="gpt-5-mini"),
            tool_specs_provider=lambda: [],
            dynamic_blocks_provider=lambda _s: [],
        )


def test_create_openai_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    model = create_model(
        "openai",
        config=OperatorConfig(
            openai_model_name="gpt-5-mini",
            openai_reasoning_effort="medium",
        ),
        tool_specs_provider=lambda: [],
        dynamic_blocks_provider=lambda _s: [],
        composer=PromptComposer(),
    )
    assert isinstance(model, OpenAIResponsesModel)
    assert model._model_name == "gpt-5-mini"
    assert model._reasoning_effort == "medium"


def test_create_anthropic_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    model = create_model(
        "anthropic",
        config=OperatorConfig(
            anthropic_model_name="claude-sonnet-4-6",
            anthropic_thinking="adaptive",
            anthropic_thinking_effort="medium",
        ),
        tool_specs_provider=lambda: [],
        dynamic_blocks_provider=lambda _s: [],
        composer=PromptComposer(),
    )
    assert isinstance(model, AnthropicModel)
    assert model._model_name == "claude-sonnet-4-6"
    assert model._thinking_mode == "adaptive"
    assert model._thinking_effort == "medium"


def test_model_label() -> None:
    assert model_label("simple") == "simple (deterministic)"
    assert "deepseek-v4-flash" in model_label(
        "deepseek",
        config=OperatorConfig(deepseek_model_name=DEFAULT_MODEL),
    )
    assert "claude-sonnet-4-6" in model_label(
        "anthropic",
        config=OperatorConfig(anthropic_model_name="claude-sonnet-4-6"),
    )
    assert "gpt-5-mini" in model_label(
        "openai",
        config=OperatorConfig(openai_model_name="gpt-5-mini"),
    )
