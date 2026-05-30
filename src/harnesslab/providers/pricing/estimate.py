"""Estimate call cost from canonical usage + catalog schedules."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from harnesslab.providers.pricing.catalog import load_pricing_catalog, resolve_schedule
from harnesslab.providers.pricing.fx import usd_per_unit_for
from harnesslab.providers.pricing.models import (
    CanonicalUsage,
    CostResult,
    CostSource,
    PricingSchedule,
)
from harnesslab.providers.pricing.normalize import normalize_usage
from harnesslab.providers.pricing.tiers import effective_rates_for_usage

_ONE_MILLION = Decimal("1000000")

# Legacy flat table — used when catalog miss or degraded one-shot estimate.
_LEGACY_FLAT_USD: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (0.435, 0.87),
    "mimo-v2.5": (0.14, 0.28),
    "mimo-v2.5-pro": (0.435, 0.87),
    "claude-sonnet-4-6": (3.0, 15.0),
    "gpt-5-mini": (0.25, 2.0),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-3-flash-preview": (0.15, 0.60),
    "simple": (0.0, 0.0),
}


def _legacy_flat_cost(model_name: str | None, usage: CanonicalUsage) -> float:
    if not model_name:
        return 0.0
    key = model_name.strip().lower()
    rates = _LEGACY_FLAT_USD.get(key)
    if rates is None:
        for candidate, candidate_rates in _LEGACY_FLAT_USD.items():
            if candidate in key:
                rates = candidate_rates
                break
    if rates is None:
        return 0.0
    in_rate, out_rate = rates
    prompt = usage.prompt_tokens or usage.input
    resp = usage.output + usage.reasoning
    return (prompt * in_rate + resp * out_rate) / 1_000_000.0


def _schedule_amount_native(
    usage: CanonicalUsage,
    schedule: PricingSchedule,
) -> tuple[float, list[str]]:
    rates = effective_rates_for_usage(schedule, input_tokens=usage.input)
    amount = 0.0
    missing_rates: list[str] = []
    breakdown = usage.to_breakdown()
    for dimension, tokens in breakdown.items():
        rate = rates.get(dimension)
        if rate is None:
            rate = rates.get("input")
            if rate is None:
                missing_rates.append(dimension)
                continue
            missing_rates.append(dimension)
        amount += tokens * rate / 1_000_000.0
    return amount, missing_rates


def _schedule_amount_native_decimal(
    usage: CanonicalUsage,
    schedule: PricingSchedule,
) -> tuple[Decimal, list[str]]:
    rates = effective_rates_for_usage(schedule, input_tokens=usage.input)
    amount = Decimal("0")
    missing_rates: list[str] = []
    for dimension, tokens in usage.to_breakdown().items():
        rate = rates.get(dimension)
        if rate is None:
            rate = rates.get("input")
            if rate is None:
                missing_rates.append(dimension)
                continue
            missing_rates.append(dimension)
        amount += Decimal(tokens) * Decimal(str(rate)) / _ONE_MILLION
    return amount, missing_rates


def estimate_call_cost(
    *,
    model_name: str | None,
    usage: CanonicalUsage,
    currency: str | None = None,
    at: datetime | None = None,
) -> CostResult:
    """Estimate call cost; ``amount_usd`` always feeds the budget ledger."""

    at = at or datetime.now(UTC)
    schedule = resolve_schedule(model_name, currency=currency, at=at)
    catalog = load_pricing_catalog()

    if schedule is None:
        amount = _legacy_flat_cost(model_name, usage)
        if amount <= 0:
            return CostResult(
                amount_usd=None,
                status="unknown",
                source="none",
                pricing_version=catalog.pricing_version,
                notes=("no matching schedule",),
            )
        return CostResult(
            amount_usd=round(amount, 8),
            status="estimated",
            source="legacy_flat",
            pricing_version=catalog.pricing_version,
            amount_native=round(amount, 8),
            notes=("catalog miss; used legacy input/output table",),
        )

    amount_native, missing_rates = _schedule_amount_native(usage, schedule)
    notes: list[str] = []
    if schedule.tiered_rates:
        notes.append("tiered_rates applied by billable input token count")
    if missing_rates:
        notes.append(f"dimensions without explicit rate: {', '.join(sorted(set(missing_rates)))}")
    if schedule.notes:
        notes.append(schedule.notes)

    if amount_native <= 0 and not usage.to_breakdown():
        return CostResult(
            amount_usd=0.0,
            status="estimated",
            source=_cost_source(schedule),
            schedule_id=schedule.id,
            pricing_version=catalog.pricing_version,
            currency=schedule.currency,
            amount_native=0.0,
            notes=tuple(notes),
        )

    rate = usd_per_unit_for(schedule.currency, catalog.usd_per_unit)
    if schedule.currency == "USD":
        amount_usd = amount_native
    elif rate is None:
        notes.append(
            f"missing usd_per_unit for {schedule.currency}; amount_usd unavailable"
        )
        amount_usd = None
    else:
        amount_usd = amount_native * rate

    return CostResult(
        amount_usd=round(amount_usd, 8) if amount_usd is not None else None,
        status="unknown" if missing_rates and amount_native <= 0 else "estimated",
        source=_cost_source(schedule),
        schedule_id=schedule.id,
        pricing_version=catalog.pricing_version,
        currency=schedule.currency,
        amount_native=round(amount_native, 8),
        notes=tuple(notes),
    )


def estimate_call_cost_decimal(
    *,
    model_name: str | None,
    usage: CanonicalUsage,
    currency: str | None = None,
    at: datetime | None = None,
) -> Decimal | None:
    """Deterministic Decimal USD estimate for eval pins (no float drift)."""

    at = at or datetime.now(UTC)
    schedule = resolve_schedule(model_name, currency=currency, at=at)
    catalog = load_pricing_catalog()
    if schedule is None:
        legacy = Decimal(str(_legacy_flat_cost(model_name, usage)))
        return legacy if legacy > 0 else None

    amount_native, _ = _schedule_amount_native_decimal(usage, schedule)
    if schedule.currency == "USD":
        return amount_native
    rate = usd_per_unit_for(schedule.currency, catalog.usd_per_unit)
    if rate is None:
        return None
    return amount_native * Decimal(str(rate))


def _cost_source(schedule: PricingSchedule) -> CostSource:
    return cast(CostSource, "user_override" if schedule.source == "user_override" else "catalog")


def estimate_call_cost_usd(
    *,
    model_name: str | None,
    request_tokens: int | None,
    response_tokens: int | None,
) -> float:
    """Backward-compatible wrapper used by loop budget accumulation."""

    usage = CanonicalUsage(
        input=max(int(request_tokens or 0), 0),
        output=max(int(response_tokens or 0), 0),
    )
    result = estimate_call_cost(model_name=model_name, usage=usage)
    return float(result.amount_usd or 0.0)


def estimate_from_raw_usage(
    *,
    model_name: str | None,
    raw_usage: dict | None,
    provider: str | None = None,
    api_mode: str = "unknown",
) -> tuple[CanonicalUsage, CostResult]:
    usage = normalize_usage(raw_usage, provider=provider, api_mode=api_mode)  # type: ignore[arg-type]
    result = estimate_call_cost(model_name=model_name, usage=usage)
    return usage, result
