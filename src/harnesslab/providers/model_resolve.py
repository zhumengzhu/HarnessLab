"""DeepSeek model name resolution (shared by config + provider)."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


def resolve_deepseek_model_name(
    *,
    model_name: str | None = None,
    config: Any | None = None,
) -> str:
    """Resolve API model id from explicit arg, env, or operator config."""

    if model_name:
        return model_name.strip()
    env = os.getenv("DEEPSEEK_MODEL")
    if env:
        return env.strip()
    configured = getattr(config, "deepseek_model_name", None) if config is not None else None
    if configured:
        return str(configured).strip()
    return DEFAULT_DEEPSEEK_MODEL
