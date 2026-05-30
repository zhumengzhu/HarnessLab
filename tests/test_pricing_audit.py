"""Tests for pricing catalog audit."""

from __future__ import annotations

from harnesslab.providers.pricing import (
    audit_pricing_catalog,
    format_audit_report,
    reset_pricing_cache,
)


def test_audit_pricing_catalog_covers_builtin_models() -> None:
    reset_pricing_cache()
    report = audit_pricing_catalog(currency="USD")
    assert report["schedule_count"] >= 1
    assert "deepseek-v4-flash" not in report["missing_model_ids"]
    text = format_audit_report(report)
    assert "pricing_version:" in text
    assert "fingerprint:" in text
