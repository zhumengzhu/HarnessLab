"""Currency conversion helpers for pricing estimates and Usage display."""

from __future__ import annotations

from typing import Any

# Legacy operator/catalog key; prefer ``usd_per_unit``.
_LEGACY_USD_PER_UNIT_KEY = "fx_to_usd"


def usd_per_unit_for(currency: str, usd_per_unit: dict[str, float]) -> float | None:
    """Return USD value of one unit of ``currency`` (e.g. 1 CNY → 0.14 USD)."""

    code = currency.strip().upper()
    if code == "USD":
        return 1.0
    rate = usd_per_unit.get(code)
    if rate is None or rate <= 0:
        return None
    return rate


def usd_to_display(
    amount_usd: float,
    *,
    display_currency: str,
    usd_per_unit: dict[str, float],
) -> float | None:
    code = display_currency.strip().upper()
    if code == "USD":
        return round(amount_usd, 6)
    rate = usd_per_unit_for(code, usd_per_unit)
    if rate is None or rate <= 0:
        return None
    return round(amount_usd / rate, 6)


def merge_usd_per_unit_tables(*tables: dict[str, float]) -> dict[str, float]:
    merged: dict[str, float] = {"USD": 1.0}
    for table in tables:
        for code, rate in table.items():
            if rate > 0:
                merged[code.upper()] = rate
    return merged


def parse_usd_per_unit_table(value: Any) -> dict[str, float]:
    """Parse top-level ``usd_per_unit`` object from operator config."""

    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, rate in value.items():
        if not isinstance(key, str):
            continue
        try:
            parsed = float(rate)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            out[key.upper()] = parsed
    return out


def usd_per_unit_table_from_config(raw: dict[str, Any]) -> dict[str, float]:
    """Read ``usd_per_unit`` table; fall back to legacy ``fx_to_usd``."""

    table = parse_usd_per_unit_table(raw.get("usd_per_unit"))
    if table:
        return table
    return parse_usd_per_unit_table(raw.get(_LEGACY_USD_PER_UNIT_KEY))


def currency_symbols_from_catalog(raw_currencies: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(raw_currencies, dict):
        return {"USD": "$"}
    out: dict[str, str] = {}
    for code, meta in raw_currencies.items():
        if not isinstance(code, str):
            continue
        symbol = code
        if isinstance(meta, dict):
            raw_symbol = meta.get("symbol")
            if isinstance(raw_symbol, str) and raw_symbol.strip():
                symbol = raw_symbol.strip()
        out[code.upper()] = symbol
    out.setdefault("USD", "$")
    return out
