"""Tests for tiered pricing schedules."""

from __future__ import annotations

from decimal import Decimal

import pytest

from harnesslab.providers.pricing import (
    CanonicalUsage,
    estimate_call_cost,
    reset_pricing_cache,
)
from harnesslab.providers.pricing.parse import schedule_from_dict
from harnesslab.providers.pricing.tiers import select_pricing_tier


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_pricing_cache()
    yield
    reset_pricing_cache()


def _tiered_schedule():
    return schedule_from_dict(
        {
            "id": "demo-tiered-usd",
            "model_id": "demo-tiered",
            "provider": "demo",
            "currency": "USD",
            "tiered_rates": [
                {
                    "range": [0, 128_000],
                    "rates_per_million": {"input": 3.0, "output": 15.0},
                },
                {
                    "range": [128_000, 1_000_000],
                    "rates_per_million": {"input": 6.0, "output": 30.0},
                },
            ],
        }
    )


def test_select_pricing_tier_half_open_ranges() -> None:
    schedule = _tiered_schedule()
    low = select_pricing_tier(schedule.tiered_rates, 64_000)
    high = select_pricing_tier(schedule.tiered_rates, 200_000)
    assert low is not None and low.rates_per_million["input"] == 3.0
    assert high is not None and high.rates_per_million["input"] == 6.0


def test_tiered_override_applies_high_input_rate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps(
            {
                "overrides": [
                    {
                        "id": "demo-tiered-usd",
                        "model_id": "demo-tiered",
                        "provider": "demo",
                        "currency": "USD",
                        "tiered_rates": [
                            {
                                "range": [0, 128_000],
                                "rates_per_million": {"input": 3.0, "output": 15.0},
                            },
                            {
                                "range": [128_000, 1_000_000],
                                "rates_per_million": {"input": 6.0, "output": 30.0},
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESSLAB_PRICING_CONFIG", str(path))

    usage = CanonicalUsage(input=200_000, output=0)
    result = estimate_call_cost(model_name="demo-tiered", usage=usage)
    assert result.amount_usd is not None
    assert abs(result.amount_usd - 1.2) < 1e-9


def test_estimate_call_cost_decimal_matches_float_for_flat_rate() -> None:
    from harnesslab.providers.pricing.estimate import estimate_call_cost_decimal

    usage = CanonicalUsage(input=1_000_000, output=0)
    decimal_cost = estimate_call_cost_decimal(model_name="deepseek-v4-flash", usage=usage)
    float_cost = estimate_call_cost(model_name="deepseek-v4-flash", usage=usage).amount_usd
    assert decimal_cost == Decimal("0.14")
    assert float_cost == 0.14
