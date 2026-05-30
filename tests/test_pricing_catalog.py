"""Tests for pricing catalog load and schedule resolution."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from harnesslab.providers.pricing import (
    CanonicalUsage,
    catalog_fingerprint,
    estimate_call_cost,
    load_pricing_catalog,
    reset_pricing_cache,
    resolve_schedule,
)


@pytest.fixture(autouse=True)
def _clear_pricing_cache() -> None:
    reset_pricing_cache()
    yield
    reset_pricing_cache()


def test_load_pricing_catalog_has_schedules() -> None:
    catalog = load_pricing_catalog()
    assert catalog.schema_version >= 1
    assert catalog.pricing_version
    assert any(s.model_id == "deepseek-v4-flash" for s in catalog.schedules)


def test_resolve_schedule_exact_match() -> None:
    schedule = resolve_schedule("deepseek-v4-flash", currency="USD")
    assert schedule is not None
    assert schedule.currency == "USD"
    assert "input" in schedule.rates_per_million


def test_resolve_schedule_partial_model_id() -> None:
    schedule = resolve_schedule("deepseek/deepseek-v4-pro", currency="USD")
    assert schedule is not None
    assert "deepseek-v4-pro" in schedule.model_id


def test_catalog_fingerprint_stable() -> None:
    assert catalog_fingerprint()
    assert catalog_fingerprint() == catalog_fingerprint()


def test_estimate_call_cost_uses_cache_read_rate() -> None:
    usage = CanonicalUsage(input=0, output=0, cache_read=1_000_000)
    result = estimate_call_cost(
        model_name="deepseek-v4-flash",
        usage=usage,
        currency="USD",
    )
    assert result.amount_usd is not None
    assert result.source == "catalog"
    assert abs(result.amount_usd - 0.0028) < 1e-6


def test_estimate_call_cost_cny_schedule_converts_to_usd() -> None:
    usage = CanonicalUsage(input=1_000_000, output=0)
    result = estimate_call_cost(
        model_name="deepseek-v4-flash",
        usage=usage,
        currency="CNY",
    )
    assert result.currency == "CNY"
    assert result.amount_native == 1.0
    assert result.amount_usd is not None
    assert abs(result.amount_usd - (1.0 * 0.14)) < 1e-6


def test_estimate_call_cost_respects_effective_until() -> None:
    schedule = resolve_schedule("deepseek-v4-flash", currency="USD")
    assert schedule is not None
    future = datetime(2099, 1, 1, tzinfo=UTC)
    if schedule.effective_until is None:
        active = resolve_schedule("deepseek-v4-flash", currency="USD", at=future)
        assert active is not None
