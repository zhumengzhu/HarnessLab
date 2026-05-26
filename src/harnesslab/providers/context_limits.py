"""Align loop ``RuntimeLimits`` with catalog ``context_window`` per model."""

from __future__ import annotations

from dataclasses import replace

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.operator_config import OperatorConfig
from harnesslab.providers.catalog import ModelCatalog
from harnesslab.providers.model_resolve import (
    resolve_anthropic_model_name,
    resolve_deepseek_model_name,
    resolve_gemini_model_name,
    resolve_openai_model_name,
)

# Compaction triggers at this fraction of the model context window.
_COMPACTION_RATIO = 0.85


def model_id_for_backend(
    backend: str,
    *,
    config: OperatorConfig | None,
) -> str | None:
    if config is None or backend == "simple":
        return None
    if backend == "deepseek":
        return resolve_deepseek_model_name(config=config)
    if backend == "anthropic":
        return resolve_anthropic_model_name(config=config)
    if backend == "openai":
        return resolve_openai_model_name(config=config)
    if backend == "gemini":
        return resolve_gemini_model_name(config=config)
    return None


def catalog_context_window(model_id: str | None) -> int | None:
    if not model_id:
        return None
    try:
        entry = ModelCatalog().get(model_id)
    except KeyError:
        return None
    if entry.context_window <= 0:
        return None
    return entry.context_window


def align_runtime_limits_with_model(
    limits: RuntimeLimits,
    *,
    backend: str,
    config: OperatorConfig | None,
    model_id: str | None = None,
) -> RuntimeLimits:
    """Set ``context_window_tokens`` to the catalog maximum for ``model_id``.

    HarnessLab uses the model's official context cap for the context ring,
    compaction threshold, and overflow recovery — not a smaller MVP default.
    Operator ``limits`` in config still control output caps, shell timeouts,
    etc.; only context/compaction fields are overridden here.
    """

    resolved_id = model_id or model_id_for_backend(backend, config=config)
    window = catalog_context_window(resolved_id)
    if window is None:
        return limits
    threshold = max(1, int(window * _COMPACTION_RATIO))
    return replace(
        limits,
        context_window_tokens=window,
        compaction_threshold_tokens=threshold,
    )


def format_context_window(tokens: int) -> str:
    if tokens >= 1_048_576 and tokens % 1_048_576 == 0:
        return f"{tokens // 1_048_576}M"
    if tokens >= 1_000_000:
        millions = tokens / 1_000_000
        if millions == int(millions):
            return f"{int(millions)}M"
        return f"{millions:.1f}M"
    if tokens >= 1000:
        return f"{round(tokens / 1000)}K"
    return str(tokens)
