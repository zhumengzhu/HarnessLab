"""Tests for Phase 4.1 provider registry."""

from __future__ import annotations

import pytest

from harnesslab.core.operator_config import OperatorConfig
from harnesslab.core.prompt import PromptComposer
from harnesslab.core.simple_model import SimpleModel
from harnesslab.providers.deepseek import DEFAULT_MODEL, DeepSeekModel
from harnesslab.providers.registry import (
    create_model,
    model_label,
    normalize_backend,
)


def test_normalize_backend_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown model backend"):
        normalize_backend("openai")


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


def test_model_label() -> None:
    assert model_label("simple") == "simple (deterministic)"
    assert "deepseek-v4-flash" in model_label(
        "deepseek",
        config=OperatorConfig(deepseek_model_name=DEFAULT_MODEL),
    )
