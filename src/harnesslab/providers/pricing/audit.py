"""Pricing catalog audit helpers (compare model catalog vs price schedules)."""

from __future__ import annotations

from typing import Any

from harnesslab.providers.catalog import ModelCatalog
from harnesslab.providers.pricing.catalog import catalog_fingerprint, load_pricing_catalog


def audit_pricing_catalog(*, currency: str = "USD") -> dict[str, Any]:
    """Report model IDs missing USD/CNY schedules and orphan price rows."""

    target = currency.strip().upper()
    model_catalog = ModelCatalog()
    pricing = load_pricing_catalog()
    model_ids = set(model_catalog.list_model_ids())

    schedules = [s for s in pricing.schedules if s.currency == target]
    priced_models = {s.model_id for s in schedules}

    missing_model_ids = sorted(model_id for model_id in model_ids if model_id not in priced_models)
    orphan_schedules = sorted(
        s.id for s in schedules if s.model_id not in model_ids and s.model_id != "simple"
    )
    tiered_schedule_ids = sorted(s.id for s in schedules if s.tiered_rates)

    return {
        "pricing_version": pricing.pricing_version,
        "fingerprint": catalog_fingerprint(),
        "currency": target,
        "schedule_count": len(schedules),
        "model_catalog_count": len(model_ids),
        "missing_model_ids": missing_model_ids,
        "orphan_schedule_ids": orphan_schedules,
        "tiered_schedule_ids": tiered_schedule_ids,
    }


def format_audit_report(report: dict[str, Any]) -> str:
    lines = [
        f"pricing_version: {report.get('pricing_version')}",
        f"fingerprint: {report.get('fingerprint')}",
        f"currency: {report.get('currency')}",
        f"schedules: {report.get('schedule_count')} "
        f"(tiered: {len(report.get('tiered_schedule_ids', []))})",
    ]
    missing = report.get("missing_model_ids") or []
    if missing:
        lines.append(f"missing_model_ids ({len(missing)}): {', '.join(missing)}")
    else:
        lines.append("missing_model_ids: none")
    orphans = report.get("orphan_schedule_ids") or []
    if orphans:
        lines.append(f"orphan_schedule_ids ({len(orphans)}): {', '.join(orphans)}")
    else:
        lines.append("orphan_schedule_ids: none")
    tiered = report.get("tiered_schedule_ids") or []
    if tiered:
        lines.append(f"tiered_schedule_ids: {', '.join(tiered)}")
    return "\n".join(lines)
