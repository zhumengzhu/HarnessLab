"""Pricing domain models (HarnessLab Phase 5.10+)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

CostStatus = Literal["estimated", "unknown", "included"]
CostSource = Literal[
    "catalog",
    "legacy_flat",
    "user_override",
    "none",
]

# Canonical billing dimensions. Not every model uses every key.
CANONICAL_DIMENSIONS = (
    "input",
    "output",
    "cache_read",
    "cache_write",
    "cache_write_5m",
    "cache_write_1h",
    "reasoning",
)


@dataclass(frozen=True)
class CanonicalUsage:
    """Provider-normalized token buckets for one model call."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    reasoning: int = 0

    def to_breakdown(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for key in CANONICAL_DIMENSIONS:
            value = getattr(self, key)
            if value > 0:
                out[key] = value
        return out

    @classmethod
    def from_breakdown(cls, raw: dict[str, Any] | None) -> CanonicalUsage:
        if not isinstance(raw, dict):
            return cls()
        kwargs = {key: int(raw.get(key, 0) or 0) for key in CANONICAL_DIMENSIONS}
        return cls(**kwargs)

    @property
    def prompt_tokens(self) -> int:
        return (
            self.input
            + self.cache_read
            + self.cache_write
            + self.cache_write_5m
            + self.cache_write_1h
        )

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output + self.reasoning


@dataclass(frozen=True)
class CostResult:
    amount_usd: float | None
    status: CostStatus
    source: CostSource
    schedule_id: str | None = None
    pricing_version: str | None = None
    currency: str = "USD"
    amount_native: float | None = None
    notes: tuple[str, ...] = ()

    def to_trace_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "amount_usd": self.amount_usd,
            "status": self.status,
            "source": self.source,
            "schedule_id": self.schedule_id,
            "pricing_version": self.pricing_version,
            "currency": self.currency,
            "notes": list(self.notes),
        }
        if self.amount_native is not None:
            payload["amount_native"] = self.amount_native
        return payload


@dataclass(frozen=True)
class PricingTier:
    """Half-open input-token tier ``[range_start, range_end)`` with per-M rates."""

    range_start: int
    range_end: int
    rates_per_million: dict[str, float]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PricingTier:
        range_raw = raw.get("range")
        if not isinstance(range_raw, list) or len(range_raw) < 1:
            raise ValueError("tiered_rates[].range must be [start, end?)")
        start = int(range_raw[0])
        end = int(range_raw[1]) if len(range_raw) > 1 else 2**63
        rates = raw.get("rates_per_million") or {}
        if not isinstance(rates, dict) or not rates:
            raise ValueError("tiered_rates[].rates_per_million must be a non-empty object")
        return cls(
            range_start=max(start, 0),
            range_end=max(end, start + 1),
            rates_per_million={str(k): float(v) for k, v in rates.items()},
        )


@dataclass(frozen=True)
class PricingSchedule:
    id: str
    model_id: str
    provider: str
    currency: str
    dimensions: tuple[str, ...]
    rates_per_million: dict[str, float]
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    source: str = "catalog"
    source_url: str | None = None
    notes: str | None = None
    tiered_rates: tuple[PricingTier, ...] = ()

    def is_active_at(self, at: datetime | None) -> bool:
        if at is None:
            return True
        if self.effective_from is not None and at < self.effective_from:
            return False
        return not (self.effective_until is not None and at >= self.effective_until)


@dataclass
class PricingCatalog:
    schema_version: int
    pricing_version: str
    default_currency: str
    schedules: list[PricingSchedule] = field(default_factory=list)
    currencies: dict[str, dict[str, Any]] = field(default_factory=dict)
    usd_per_unit: dict[str, float] = field(default_factory=dict)
