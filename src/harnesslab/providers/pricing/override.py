"""Load optional operator pricing overrides from ``~/.config/harnesslab/pricing.json``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from harnesslab.providers.pricing.fx import usd_per_unit_table_from_config
from harnesslab.providers.pricing.models import PricingSchedule
from harnesslab.providers.pricing.parse import schedule_from_dict

DEFAULT_PRICING_OVERRIDE_PATH = Path.home() / ".config" / "harnesslab" / "pricing.json"


def pricing_override_path_from_env() -> Path:
    raw = os.environ.get("HARNESSLAB_PRICING_CONFIG", "").strip()
    return Path(raw) if raw else DEFAULT_PRICING_OVERRIDE_PATH


@dataclass(frozen=True)
class PricingOverrideConfig:
    display_currency: str = "USD"
    default_currency: str | None = None
    usd_per_unit: dict[str, float] = field(default_factory=dict)
    schedules: tuple[PricingSchedule, ...] = ()


@lru_cache(maxsize=1)
def load_pricing_overrides() -> PricingOverrideConfig:
    path = pricing_override_path_from_env()
    if not path.is_file():
        return PricingOverrideConfig()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return PricingOverrideConfig()

    display = str(raw.get("display_currency", "USD")).strip().upper() or "USD"
    default_raw = raw.get("default_currency")
    default_currency = (
        str(default_raw).strip().upper()
        if isinstance(default_raw, str) and default_raw.strip()
        else None
    )

    schedules: list[PricingSchedule] = []
    for item in raw.get("overrides", []):
        if not isinstance(item, dict):
            continue
        payload = dict(item)
        payload.setdefault("source", "user_override")
        schedules.append(schedule_from_dict(payload))

    return PricingOverrideConfig(
        display_currency=display,
        default_currency=default_currency,
        usd_per_unit=usd_per_unit_table_from_config(raw),
        schedules=tuple(schedules),
    )


def merge_schedules(
    built_in: list[PricingSchedule],
    overrides: tuple[PricingSchedule, ...],
) -> list[PricingSchedule]:
    """Replace built-in rows when override matches ``(model_id, currency)``."""

    if not overrides:
        return list(built_in)
    override_keys = {(s.model_id, s.currency) for s in overrides}
    merged = [s for s in built_in if (s.model_id, s.currency) not in override_keys]
    merged.extend(overrides)
    return merged


def reset_pricing_overrides_cache() -> None:
    load_pricing_overrides.cache_clear()
