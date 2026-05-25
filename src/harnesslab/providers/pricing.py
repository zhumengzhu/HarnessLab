"""Provider price table for session cost budgeting (Phase 5.10)."""

from __future__ import annotations

# USD per 1M tokens (input, output). Estimates for budget guardrails only.
_PRICE_PER_MILLION: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.27, 1.10),
    "deepseek-v4-pro": (0.55, 2.19),
    "claude-sonnet-4-6": (3.0, 15.0),
    "gpt-5-mini": (0.25, 2.0),
    "gemini-2.5-flash": (0.15, 0.60),
    "simple": (0.0, 0.0),
}


def estimate_call_cost_usd(
    *,
    model_name: str | None,
    request_tokens: int | None,
    response_tokens: int | None,
) -> float:
    """Estimate USD cost for one model call from token counts."""

    if not model_name:
        return 0.0
    key = model_name.strip().lower()
    prices = _PRICE_PER_MILLION.get(key)
    if prices is None:
        for candidate, rate in _PRICE_PER_MILLION.items():
            if candidate in key:
                prices = rate
                break
    if prices is None:
        return 0.0
    in_rate, out_rate = prices
    req = max(int(request_tokens or 0), 0)
    resp = max(int(response_tokens or 0), 0)
    return (req * in_rate + resp * out_rate) / 1_000_000.0
