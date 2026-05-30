"""Tests for provider price-table cost estimates (Phase 5.10)."""

from __future__ import annotations

from harnesslab.providers.catalog import ModelCatalog
from harnesslab.providers.pricing import estimate_call_cost_usd


def test_estimate_call_cost_deepseek_flash() -> None:
    cost = estimate_call_cost_usd(
        model_name="deepseek-v4-flash",
        request_tokens=1_000_000,
        response_tokens=0,
    )
    assert cost == 0.14


def test_estimate_call_cost_combined_tokens() -> None:
    cost = estimate_call_cost_usd(
        model_name="deepseek-v4-flash",
        request_tokens=1000,
        response_tokens=1000,
    )
    assert abs(cost - 0.00042) < 1e-9


def test_estimate_call_cost_unknown_model_returns_zero() -> None:
    assert (
        estimate_call_cost_usd(
            model_name="unknown-model-xyz",
            request_tokens=10_000,
            response_tokens=10_000,
        )
        == 0.0
    )


def test_estimate_call_cost_partial_model_id_match() -> None:
    cost = estimate_call_cost_usd(
        model_name="deepseek/deepseek-v4-pro",
        request_tokens=1_000_000,
        response_tokens=1_000_000,
    )
    assert abs(cost - (0.435 + 0.87)) < 1e-9


def test_mimo_v25_cny_pricing() -> None:
    from harnesslab.providers.pricing import CanonicalUsage, estimate_call_cost

    usage = CanonicalUsage(input=1_000_000, output=1_000_000, cache_read=1_000_000)
    result = estimate_call_cost(model_name="mimo-v2.5", usage=usage, currency="CNY")
    assert result.currency == "CNY"
    assert result.amount_native is not None
    assert abs(result.amount_native - 3.02) < 1e-9


def test_catalog_models_have_non_negative_estimates() -> None:
    catalog = ModelCatalog()
    for model_id in catalog.list_model_ids():
        cost = estimate_call_cost_usd(
            model_name=model_id,
            request_tokens=1000,
            response_tokens=1000,
        )
        assert cost >= 0.0


def test_gemini_3_flash_preview_has_pricing() -> None:
    cost = estimate_call_cost_usd(
        model_name="gemini-3-flash-preview",
        request_tokens=1000,
        response_tokens=1000,
    )
    assert cost > 0.0
