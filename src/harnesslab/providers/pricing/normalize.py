"""Normalize provider usage payloads into canonical billing dimensions."""

from __future__ import annotations

from typing import Any, Literal

from harnesslab.providers.pricing.models import CanonicalUsage

ApiMode = Literal[
    "anthropic_messages",
    "openai_chat",
    "openai_responses",
    "gemini",
    "unknown",
]


def _to_int(value: Any) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _dict_usage(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


def normalize_usage(
    raw_usage: Any,
    *,
    provider: str | None = None,
    api_mode: ApiMode = "unknown",
) -> CanonicalUsage:
    """Map vendor usage objects to :class:`CanonicalUsage`.

    Inspired by Hermes ``normalize_usage`` and OpenCode ``getUsage`` cache
    subtraction rules — kept intentionally smaller than upstream copies.
    """

    usage = _dict_usage(raw_usage)
    if not usage:
        return CanonicalUsage()

    provider_name = (provider or "").strip().lower()
    mode = api_mode

    if mode == "anthropic_messages" or provider_name == "anthropic":
        cache_read = _to_int(usage.get("cache_read_input_tokens"))
        cache_creation = _dict_usage(usage.get("cache_creation"))
        write_5m = _to_int(cache_creation.get("ephemeral_5m_input_tokens"))
        write_1h = _to_int(cache_creation.get("ephemeral_1h_input_tokens"))
        cache_write_total = _to_int(usage.get("cache_creation_input_tokens"))
        if write_5m > 0 or write_1h > 0:
            cache_write = 0
        else:
            cache_write = cache_write_total
            write_5m = 0
            write_1h = 0
        return CanonicalUsage(
            input=_to_int(usage.get("input_tokens")),
            output=_to_int(usage.get("output_tokens")),
            cache_read=cache_read,
            cache_write=cache_write,
            cache_write_5m=write_5m,
            cache_write_1h=write_1h,
        )

    if mode == "openai_responses" or provider_name in {"openai", "codex"}:
        input_total = _to_int(usage.get("input_tokens"))
        output_tokens = _to_int(usage.get("output_tokens"))
        details = usage.get("input_tokens_details")
        details_dict = _dict_usage(details)
        cache_read = _to_int(details_dict.get("cached_tokens"))
        cache_write = _to_int(details_dict.get("cache_creation_tokens"))
        input_tokens = max(0, input_total - cache_read - cache_write)
        output_details = _dict_usage(usage.get("output_tokens_details"))
        reasoning = _to_int(output_details.get("reasoning_tokens"))
        return CanonicalUsage(
            input=input_tokens,
            output=output_tokens,
            cache_read=cache_read,
            cache_write=cache_write,
            reasoning=reasoning,
        )

    if mode == "gemini" or provider_name in {"google", "gemini"}:
        prompt = _to_int(usage.get("promptTokenCount") or usage.get("prompt_token_count"))
        output = _to_int(
            usage.get("candidatesTokenCount") or usage.get("candidates_token_count")
        )
        thoughts = _to_int(usage.get("thoughtsTokenCount") or usage.get("thoughts_token_count"))
        return CanonicalUsage(input=prompt, output=output, reasoning=thoughts)

    # OpenAI chat / DeepSeek / generic OpenAI-compatible
    prompt_total = _to_int(usage.get("prompt_tokens"))
    output_tokens = _to_int(usage.get("completion_tokens") or usage.get("output_tokens"))
    details = _dict_usage(usage.get("prompt_tokens_details"))
    cache_read = _to_int(details.get("cached_tokens"))
    if not cache_read:
        cache_read = _to_int(usage.get("prompt_cache_hit_tokens"))
    cache_write = _to_int(details.get("cache_write_tokens"))
    if not cache_write:
        cache_write = _to_int(usage.get("cache_creation_input_tokens"))
    input_tokens = max(0, prompt_total - cache_read - cache_write)
    output_details = _dict_usage(usage.get("completion_tokens_details"))
    reasoning = _to_int(output_details.get("reasoning_tokens"))
    return CanonicalUsage(
        input=input_tokens,
        output=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        reasoning=reasoning,
    )


def legacy_token_fields(usage: CanonicalUsage) -> dict[str, int]:
    """Backward-compatible aggregate token counters for trace/budget."""

    request = usage.prompt_tokens
    response = usage.output + usage.reasoning
    total = usage.total_tokens
    if total <= 0:
        total = request + response
    return {
        "request_tokens": request,
        "response_tokens": response,
        "total_tokens": total,
    }
