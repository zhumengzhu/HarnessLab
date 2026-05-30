"""Shared parsing helpers for pricing catalog and override files."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from harnesslab.providers.pricing.models import PricingSchedule, PricingTier


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_tiered_rates(raw: Any) -> tuple[PricingTier, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("tiered_rates must be an array")
    return tuple(PricingTier.from_dict(item) for item in raw if isinstance(item, dict))


def schedule_from_dict(raw: dict[str, Any]) -> PricingSchedule:
    rates = raw.get("rates_per_million") or {}
    tiered = parse_tiered_rates(raw.get("tiered_rates"))
    dimensions = raw.get("dimensions") or list(rates.keys())
    if tiered and not rates:
        dim_set = {d for tier in tiered for d in tier.rates_per_million}
        dimensions = sorted(dim_set)
    return PricingSchedule(
        id=str(raw["id"]),
        model_id=str(raw["model_id"]).lower(),
        provider=str(raw.get("provider", "")).lower(),
        currency=str(raw.get("currency", "USD")).upper(),
        dimensions=tuple(str(d) for d in dimensions),
        rates_per_million={str(k): float(v) for k, v in rates.items()},
        effective_from=parse_dt(raw.get("effective_from")),
        effective_until=parse_dt(raw.get("effective_until")),
        source=str(raw.get("source", "catalog")),
        source_url=raw.get("source_url"),
        notes=raw.get("notes"),
        tiered_rates=tiered,
    )
