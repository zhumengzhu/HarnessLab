"""Provider model name resolution (shared by config + adapters)."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"


def resolve_deepseek_model_name(
    *,
    model_name: str | None = None,
    config: Any | None = None,
) -> str:
    """Resolve API model id from explicit arg, operator config, or env."""

    if model_name:
        return model_name.strip()
    configured = getattr(config, "deepseek_model_name", None) if config is not None else None
    if configured:
        return str(configured).strip()
    env = os.getenv("DEEPSEEK_MODEL")
    if env:
        return env.strip()
    return DEFAULT_DEEPSEEK_MODEL


def resolve_anthropic_model_name(
    *,
    model_name: str | None = None,
    config: Any | None = None,
) -> str:
    """Resolve Anthropic model id from explicit arg, operator config, or env."""

    if model_name:
        return model_name.strip()
    configured = getattr(config, "anthropic_model_name", None) if config is not None else None
    if configured:
        return str(configured).strip()
    env = os.getenv("ANTHROPIC_MODEL")
    if env:
        return env.strip()
    return DEFAULT_ANTHROPIC_MODEL


def resolve_openai_model_name(
    *,
    model_name: str | None = None,
    config: Any | None = None,
) -> str:
    """Resolve OpenAI model id from explicit arg, operator config, or env."""

    if model_name:
        return model_name.strip()
    configured = getattr(config, "openai_model_name", None) if config is not None else None
    if configured:
        return str(configured).strip()
    env = os.getenv("OPENAI_MODEL")
    if env:
        return env.strip()
    return DEFAULT_OPENAI_MODEL
