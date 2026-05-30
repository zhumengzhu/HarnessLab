"""Shared helpers to attach normalized usage to adapter ``last_call_meta``."""

from __future__ import annotations

from typing import Any

from harnesslab.providers.pricing import (
    estimate_from_raw_usage,
    legacy_token_fields,
    normalize_usage,
)


def usage_meta_from_response(
    raw_usage: Any,
    *,
    provider: str,
    api_mode: str,
    model_name: str,
) -> dict[str, Any]:
    usage = normalize_usage(raw_usage, provider=provider, api_mode=api_mode)  # type: ignore[arg-type]
    tokens = legacy_token_fields(usage)
    _, cost = estimate_from_raw_usage(
        model_name=model_name,
        raw_usage=raw_usage if isinstance(raw_usage, dict) else None,
        provider=provider,
        api_mode=api_mode,
    )
    meta: dict[str, Any] = {
        **tokens,
        "usage_breakdown": usage.to_breakdown(),
        "cost_estimate": cost.to_trace_dict(),
        "pricing_version": cost.pricing_version,
    }
    return meta
