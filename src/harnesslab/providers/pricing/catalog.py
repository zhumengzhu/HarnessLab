"""Load and resolve pricing schedules from ``pricing_catalog.json``."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from functools import lru_cache
from importlib import resources
from typing import Any

from harnesslab.providers.pricing.fx import merge_usd_per_unit_tables
from harnesslab.providers.pricing.models import PricingCatalog, PricingSchedule
from harnesslab.providers.pricing.override import load_pricing_overrides, merge_schedules
from harnesslab.providers.pricing.parse import schedule_from_dict

_CATALOG_FILENAME = "pricing_catalog.json"
_LEGACY_USD_PER_UNIT_KEY = "fx_to_usd"


def _parse_usd_per_unit(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def _usd_per_unit_from_currencies(raw_currencies: Any) -> dict[str, float]:
    if not isinstance(raw_currencies, dict):
        return {"USD": 1.0}
    out: dict[str, float] = {"USD": 1.0}
    for code, meta in raw_currencies.items():
        if not isinstance(code, str):
            continue
        if isinstance(meta, dict):
            rate = _parse_usd_per_unit(meta.get("usd_per_unit"))
            if rate is None:
                rate = _parse_usd_per_unit(meta.get(_LEGACY_USD_PER_UNIT_KEY))
            if rate is not None:
                out[code.upper()] = rate
    return out


@lru_cache(maxsize=1)
def load_pricing_catalog() -> PricingCatalog:
    path = resources.files("harnesslab.providers").joinpath(_CATALOG_FILENAME)
    raw = json.loads(path.read_text(encoding="utf-8"))
    built_in = [schedule_from_dict(item) for item in raw.get("schedules", [])]
    currencies_raw = raw.get("currencies", {})
    currencies = currencies_raw if isinstance(currencies_raw, dict) else {}
    usd_per_unit_catalog = _usd_per_unit_from_currencies(currencies)
    overrides = load_pricing_overrides()
    schedules = merge_schedules(built_in, overrides.schedules)
    usd_per_unit = merge_usd_per_unit_tables(usd_per_unit_catalog, overrides.usd_per_unit)
    default_currency = overrides.default_currency or str(raw.get("default_currency", "USD")).upper()
    return PricingCatalog(
        schema_version=int(raw.get("schema_version", 1)),
        pricing_version=str(raw.get("pricing_version", "unknown")),
        default_currency=default_currency,
        schedules=schedules,
        currencies=currencies,
        usd_per_unit=usd_per_unit,
    )


def reset_pricing_catalog_cache() -> None:
    load_pricing_catalog.cache_clear()


def catalog_fingerprint() -> str:
    catalog = load_pricing_catalog()
    overrides = load_pricing_overrides()
    digest = hashlib.sha256(
        json.dumps(
            {
                "schedules": [
                    {
                        "id": s.id,
                        "rates": s.rates_per_million,
                        "tiered": [
                            {"range": [t.range_start, t.range_end], "rates": t.rates_per_million}
                            for t in s.tiered_rates
                        ],
                        "effective_from": (
                            s.effective_from.isoformat() if s.effective_from else None
                        ),
                        "effective_until": (
                            s.effective_until.isoformat() if s.effective_until else None
                        ),
                    }
                    for s in catalog.schedules
                ],
                "usd_per_unit": catalog.usd_per_unit,
                "override_count": len(overrides.schedules),
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return digest.hexdigest()[:12]


def resolve_schedule(
    model_name: str | None,
    *,
    currency: str | None = None,
    at: datetime | None = None,
) -> PricingSchedule | None:
    if not model_name or not model_name.strip():
        return None
    catalog = load_pricing_catalog()
    target_currency = (currency or catalog.default_currency).upper()
    key = model_name.strip().lower()

    candidates: list[PricingSchedule] = []
    for schedule in catalog.schedules:
        if schedule.currency != target_currency:
            continue
        if not schedule.is_active_at(at):
            continue
        if schedule.model_id == key:
            candidates.append(schedule)
            continue
        if key in schedule.model_id or schedule.model_id in key:
            candidates.append(schedule)

    if not candidates:
        return None
    # Prefer user overrides, then exact id match, then longest model_id.
    candidates.sort(
        key=lambda s: (
            s.source != "user_override",
            s.model_id != key,
            -len(s.model_id),
        )
    )
    return candidates[0]
