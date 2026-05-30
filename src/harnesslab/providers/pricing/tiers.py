"""Context-length tier selection (OpenClaw-style half-open input ranges)."""

from __future__ import annotations

from harnesslab.providers.pricing.models import PricingSchedule, PricingTier


def select_pricing_tier(tiers: tuple[PricingTier, ...], input_tokens: int) -> PricingTier | None:
    if not tiers:
        return None
    sorted_tiers = sorted(tiers, key=lambda tier: tier.range_start)
    if input_tokens <= 0:
        return sorted_tiers[0]

    for tier in sorted_tiers:
        if tier.range_start <= input_tokens < tier.range_end:
            return tier

    for tier in reversed(sorted_tiers):
        if input_tokens >= tier.range_start:
            return tier

    return sorted_tiers[0]


def effective_rates_for_usage(
    schedule: PricingSchedule,
    *,
    input_tokens: int,
) -> dict[str, float]:
    """Return per-million rates for one call (tiered when configured)."""

    if schedule.tiered_rates:
        tier = select_pricing_tier(schedule.tiered_rates, input_tokens)
        if tier is not None:
            return dict(tier.rates_per_million)
    return dict(schedule.rates_per_million)
