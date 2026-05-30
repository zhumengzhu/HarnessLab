"""Tests for pricing FX helpers."""

from __future__ import annotations

import pytest

from harnesslab.providers.pricing.fx import usd_per_unit_for, usd_to_display


def test_usd_per_unit_for_usd_is_one() -> None:
    assert usd_per_unit_for("USD", {"USD": 1.0}) == 1.0


def test_usd_to_display_converts_with_usd_per_unit() -> None:
    assert usd_to_display(1.0, display_currency="USD", usd_per_unit={"USD": 1.0}) == 1.0
    cny = usd_to_display(1.4, display_currency="CNY", usd_per_unit={"CNY": 0.14})
    assert cny == pytest.approx(10.0)
