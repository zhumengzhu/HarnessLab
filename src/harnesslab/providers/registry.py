"""ModelPort factory registry (Phase 4.1).

Maps operator config + CLI backend names to concrete adapters without
leaking provider details into ``core``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from harnesslab.core.models import Session
from harnesslab.core.operator_config import OperatorConfig
from harnesslab.core.prompt import PromptBlock, PromptComposer
from harnesslab.core.simple_model import SimpleModel
from harnesslab.providers.deepseek import DeepSeekModel
from harnesslab.providers.model_resolve import resolve_deepseek_model_name

ModelBackend = Literal["simple", "deepseek"]

SUPPORTED_BACKENDS: frozenset[str] = frozenset({"simple", "deepseek"})

DynamicBlocksProvider = Callable[[Session], list[PromptBlock]]


def normalize_backend(name: str | None, *, fallback: str = "simple") -> str:
    key = (name or fallback).strip().lower()
    if key not in SUPPORTED_BACKENDS:
        known = ", ".join(sorted(SUPPORTED_BACKENDS))
        raise ValueError(f"unknown model backend {name!r} (known: {known})")
    return key


def create_model(
    backend: str,
    *,
    config: OperatorConfig | None,
    tool_specs_provider: Callable[[], list[dict[str, Any]]],
    dynamic_blocks_provider: DynamicBlocksProvider,
    composer: PromptComposer | None = None,
) -> SimpleModel | DeepSeekModel:
    """Instantiate a ``ModelPort`` for ``backend`` using operator config."""

    normalized = normalize_backend(backend)
    if normalized == "simple":
        return SimpleModel()

    model_name = resolve_deepseek_model_name(config=config)
    thinking = (config.deepseek_thinking if config else "disabled") or "disabled"
    return DeepSeekModel(
        tool_specs_provider=tool_specs_provider,
        model_name=model_name,
        thinking_mode=thinking,
        composer=composer,
        dynamic_blocks_provider=dynamic_blocks_provider,
    )


def model_label(
    backend: str,
    *,
    config: OperatorConfig | None = None,
) -> str:
    """Human-readable model description for settings / health endpoints."""

    normalized = normalize_backend(backend)
    if normalized == "simple":
        return "simple (deterministic)"
    name = resolve_deepseek_model_name(config=config)
    return f"deepseek ({name})"
