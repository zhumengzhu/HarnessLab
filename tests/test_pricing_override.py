"""Tests for pricing override file merge."""

from __future__ import annotations

import json

import pytest

from harnesslab.providers.pricing import (
    estimate_call_cost,
    load_pricing_catalog,
    reset_pricing_cache,
)
from harnesslab.providers.pricing.models import CanonicalUsage


@pytest.fixture(autouse=True)
def _clear_pricing_cache() -> None:
    reset_pricing_cache()
    yield
    reset_pricing_cache()


def test_user_override_replaces_builtin_rate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps(
            {
                "overrides": [
                    {
                        "id": "custom-deepseek-flash",
                        "model_id": "deepseek-v4-flash",
                        "provider": "deepseek",
                        "currency": "USD",
                        "rates_per_million": {"input": 0.20, "output": 1.0},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESSLAB_PRICING_CONFIG", str(path))

    schedule = load_pricing_catalog()
    match = next(
        s
        for s in schedule.schedules
        if s.model_id == "deepseek-v4-flash" and s.currency == "USD"
    )
    assert match.source == "user_override"
    assert match.rates_per_million["input"] == 0.20

    result = estimate_call_cost(
        model_name="deepseek-v4-flash",
        usage=CanonicalUsage(input=1_000_000, output=0),
    )
    assert result.source == "user_override"
    assert result.amount_usd == 0.20


def test_display_currency_from_override_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps(
            {
                "display_currency": "CNY",
                "default_currency": "CNY",
                "usd_per_unit": {"CNY": 0.14},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESSLAB_PRICING_CONFIG", str(path))

    catalog = load_pricing_catalog()
    assert catalog.default_currency == "CNY"
    assert catalog.usd_per_unit["CNY"] == 0.14


def test_legacy_fx_to_usd_key_still_loads(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps({"fx_to_usd": {"CNY": 0.14}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESSLAB_PRICING_CONFIG", str(path))

    catalog = load_pricing_catalog()
    assert catalog.usd_per_unit["CNY"] == 0.14
