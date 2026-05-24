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
from harnesslab.providers.anthropic import AnthropicModel
from harnesslab.providers.deepseek import DeepSeekModel
from harnesslab.providers.failover import FailoverModel
from harnesslab.providers.gemini import GeminiModel
from harnesslab.providers.model_resolve import (
    resolve_anthropic_model_name,
    resolve_deepseek_model_name,
    resolve_gemini_model_name,
    resolve_openai_model_name,
)
from harnesslab.providers.openai_responses import OpenAIResponsesModel
from harnesslab.telemetry.log import get_logger

ModelBackend = Literal["simple", "deepseek", "anthropic", "openai", "gemini"]

SUPPORTED_BACKENDS: frozenset[str] = frozenset(
    {"simple", "deepseek", "anthropic", "openai", "gemini"}
)
_log = get_logger("providers.registry")

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
) -> (
    SimpleModel
    | DeepSeekModel
    | AnthropicModel
    | OpenAIResponsesModel
    | GeminiModel
    | FailoverModel
):
    """Instantiate a ``ModelPort`` for ``backend`` using operator config."""

    normalized = normalize_backend(backend)
    primary = _create_single_model(
        normalized,
        config=config,
        tool_specs_provider=tool_specs_provider,
        dynamic_blocks_provider=dynamic_blocks_provider,
        composer=composer,
    )
    if config is None or not config.model_failover_enabled or not config.model_fallbacks:
        return primary

    chain: list[Any] = [primary]
    labels: list[str] = [normalized]
    for fallback_backend in config.model_fallbacks:
        fb = normalize_backend(fallback_backend)
        if fb in labels:
            continue
        chain.append(
            _create_single_model(
                fb,
                config=config,
                tool_specs_provider=tool_specs_provider,
                dynamic_blocks_provider=dynamic_blocks_provider,
                composer=composer,
            )
        )
        labels.append(fb)

    if len(chain) == 1:
        return primary

    _log.info("model failover enabled chain=%s", " -> ".join(labels))
    return FailoverModel(chain, backend_labels=labels)


def _create_single_model(
    normalized: str,
    *,
    config: OperatorConfig | None,
    tool_specs_provider: Callable[[], list[dict[str, Any]]],
    dynamic_blocks_provider: DynamicBlocksProvider,
    composer: PromptComposer | None,
) -> SimpleModel | DeepSeekModel | AnthropicModel | OpenAIResponsesModel | GeminiModel:
    if normalized == "simple":
        _log.info("model backend=simple")
        return SimpleModel()

    if normalized == "anthropic":
        model_name = resolve_anthropic_model_name(config=config)
        thinking = (config.anthropic_thinking if config else "disabled") or "disabled"
        effort = config.anthropic_thinking_effort if config else None
        _log.info(
            "model backend=anthropic model_name=%s thinking=%s effort=%s",
            model_name,
            thinking,
            effort or "-",
        )
        return AnthropicModel(
            tool_specs_provider=tool_specs_provider,
            model_name=model_name,
            thinking_mode=thinking,
            thinking_effort=effort,
            composer=composer,
            dynamic_blocks_provider=dynamic_blocks_provider,
        )

    if normalized == "openai":
        model_name = resolve_openai_model_name(config=config)
        effort = (config.openai_reasoning_effort if config else "none") or "none"
        base_url = config.openai_base_url if config else None
        _log.info(
            "model backend=openai model_name=%s reasoning_effort=%s",
            model_name,
            effort,
        )
        return OpenAIResponsesModel(
            tool_specs_provider=tool_specs_provider,
            model_name=model_name,
            reasoning_effort=effort,
            base_url=base_url,
            composer=composer,
            dynamic_blocks_provider=dynamic_blocks_provider,
        )

    if normalized == "gemini":
        model_name = resolve_gemini_model_name(config=config)
        budget = config.gemini_thinking_budget if config else None
        level = config.gemini_thinking_level if config else None
        _log.info(
            "model backend=gemini model_name=%s budget=%s level=%s",
            model_name,
            budget if budget is not None else "-",
            level or "-",
        )
        return GeminiModel(
            tool_specs_provider=tool_specs_provider,
            model_name=model_name,
            thinking_budget=budget,
            thinking_level=level,
            composer=composer,
            dynamic_blocks_provider=dynamic_blocks_provider,
        )

    model_name = resolve_deepseek_model_name(config=config)
    thinking = (config.deepseek_thinking if config else "disabled") or "disabled"
    _log.info("model backend=deepseek model_name=%s thinking=%s", model_name, thinking)
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
    if normalized == "anthropic":
        name = resolve_anthropic_model_name(config=config)
        return f"anthropic ({name})"
    if normalized == "openai":
        name = resolve_openai_model_name(config=config)
        return f"openai ({name})"
    if normalized == "gemini":
        name = resolve_gemini_model_name(config=config)
        return f"gemini ({name})"
    name = resolve_deepseek_model_name(config=config)
    return f"deepseek ({name})"
