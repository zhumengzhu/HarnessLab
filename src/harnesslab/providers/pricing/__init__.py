"""Public pricing API."""

from harnesslab.providers.pricing.audit import audit_pricing_catalog, format_audit_report
from harnesslab.providers.pricing.catalog import (
    catalog_fingerprint,
    load_pricing_catalog,
    reset_pricing_catalog_cache,
    resolve_schedule,
)
from harnesslab.providers.pricing.estimate import (
    estimate_call_cost,
    estimate_call_cost_decimal,
    estimate_call_cost_usd,
    estimate_from_raw_usage,
)
from harnesslab.providers.pricing.fx import (
    currency_symbols_from_catalog,
    merge_usd_per_unit_tables,
    usd_per_unit_for,
    usd_to_display,
)
from harnesslab.providers.pricing.models import (
    CanonicalUsage,
    CostResult,
    PricingSchedule,
    PricingTier,
)
from harnesslab.providers.pricing.normalize import legacy_token_fields, normalize_usage
from harnesslab.providers.pricing.override import (
    load_pricing_overrides,
    reset_pricing_overrides_cache,
)

__all__ = [
    "CanonicalUsage",
    "CostResult",
    "PricingSchedule",
    "PricingTier",
    "audit_pricing_catalog",
    "catalog_fingerprint",
    "currency_symbols_from_catalog",
    "estimate_call_cost",
    "estimate_call_cost_decimal",
    "estimate_call_cost_usd",
    "estimate_from_raw_usage",
    "format_audit_report",
    "legacy_token_fields",
    "load_pricing_catalog",
    "load_pricing_overrides",
    "merge_usd_per_unit_tables",
    "normalize_usage",
    "reset_pricing_catalog_cache",
    "reset_pricing_overrides_cache",
    "resolve_schedule",
    "usd_per_unit_for",
    "usd_to_display",
]


def reset_pricing_cache() -> None:
    reset_pricing_catalog_cache()
    reset_pricing_overrides_cache()
