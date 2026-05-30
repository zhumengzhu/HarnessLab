"""Aggregate token usage from trace ``model_call`` events for the Web UI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from harnesslab.core.models import Session, TraceEvent
from harnesslab.providers.pricing import (
    CanonicalUsage,
    currency_symbols_from_catalog,
    estimate_call_cost,
    load_pricing_catalog,
    load_pricing_overrides,
    usd_to_display,
)
from harnesslab.providers.pricing.models import CANONICAL_DIMENSIONS

UsageRange = Literal["today", "7d", "30d", "all"]

_EMPTY_DIMENSIONS = {key: 0 for key in CANONICAL_DIMENSIONS}


def usage_range_start(range_key: UsageRange, now: datetime) -> datetime | None:
    if range_key == "all":
        return None
    if range_key == "today":
        return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    days = {"7d": 7, "30d": 30}[range_key]
    return now.astimezone(UTC) - timedelta(days=days)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _in_range(created_at: datetime, start: datetime | None) -> bool:
    if start is None:
        return True
    return _as_utc(created_at) >= start


def _model_label(payload: dict[str, Any]) -> str:
    for key in ("model_name", "model_id", "provider"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "unknown"


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _call_tokens(payload: dict[str, Any]) -> tuple[int, int, int]:
    request_tokens = _int_or_zero(payload.get("request_tokens"))
    response_tokens = _int_or_zero(payload.get("response_tokens"))
    total_tokens = _int_or_zero(payload.get("total_tokens"))
    if total_tokens <= 0:
        total_tokens = request_tokens + response_tokens
    if request_tokens <= 0 and response_tokens <= 0 and total_tokens > 0:
        request_tokens = total_tokens
    return request_tokens, response_tokens, total_tokens


def _call_usage(payload: dict[str, Any]) -> tuple[CanonicalUsage, int, int, int]:
    breakdown = payload.get("usage_breakdown")
    if isinstance(breakdown, dict):
        usage = CanonicalUsage.from_breakdown(breakdown)
        request = usage.prompt_tokens or usage.input
        response = usage.output + usage.reasoning
        total = usage.total_tokens or (request + response)
        return usage, request, response, total
    req, resp, total = _call_tokens(payload)
    usage = CanonicalUsage(input=req, output=resp)
    return usage, req, resp, total


def _call_cost(payload: dict[str, Any], *, model: str, usage: CanonicalUsage) -> float:
    cost_estimate = payload.get("cost_estimate")
    if isinstance(cost_estimate, dict):
        amount = cost_estimate.get("amount_usd")
        if isinstance(amount, (int, float)) and amount >= 0:
            return round(float(amount), 6)
    result = estimate_call_cost(model_name=model, usage=usage)
    return round(float(result.amount_usd or 0.0), 6)


def _empty_row_template() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "llm_calls": 0,
        "dimensions": dict(_EMPTY_DIMENSIONS),
    }


def _bump_dimensions(row: dict[str, Any], usage: CanonicalUsage) -> None:
    dims = row.setdefault("dimensions", dict(_EMPTY_DIMENSIONS))
    for key, value in usage.to_breakdown().items():
        dims[key] = dims.get(key, 0) + value


def aggregate_usage_from_events(
    events: list[TraceEvent],
    *,
    range_key: UsageRange = "all",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build usage summary buckets from trace events."""

    now = now or datetime.now(UTC)
    start = usage_range_start(range_key, now)

    totals = {
        **_empty_row_template(),
        "tool_calls": 0,
        "session_count": 0,
    }
    daily: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_session: dict[str, dict[str, Any]] = {}
    session_ids: set[str] = set()

    def bump_daily(
        day: str,
        req: int,
        resp: int,
        total: int,
        cost: float,
        usage: CanonicalUsage,
    ) -> None:
        row = daily.setdefault(day, {"date": day, **_empty_row_template()})
        row["input_tokens"] += req
        row["output_tokens"] += resp
        row["total_tokens"] += total
        row["cost_usd"] = round(row["cost_usd"] + cost, 6)
        row["llm_calls"] += 1
        _bump_dimensions(row, usage)

    def bump_model(
        model: str,
        req: int,
        resp: int,
        total: int,
        cost: float,
        usage: CanonicalUsage,
    ) -> None:
        row = by_model.setdefault(model, {"model": model, **_empty_row_template()})
        row["input_tokens"] += req
        row["output_tokens"] += resp
        row["total_tokens"] += total
        row["cost_usd"] = round(row["cost_usd"] + cost, 6)
        row["llm_calls"] += 1
        _bump_dimensions(row, usage)

    def bump_session(
        session_id: str,
        req: int,
        resp: int,
        total: int,
        cost: float,
        usage: CanonicalUsage,
        at: datetime,
    ) -> None:
        row = by_session.setdefault(
            session_id,
            {
                "session_id": session_id,
                **_empty_row_template(),
                "tool_calls": 0,
                "last_activity_at": None,
            },
        )
        row["input_tokens"] += req
        row["output_tokens"] += resp
        row["total_tokens"] += total
        row["cost_usd"] = round(row["cost_usd"] + cost, 6)
        row["llm_calls"] += 1
        _bump_dimensions(row, usage)
        iso = _as_utc(at).isoformat()
        if row["last_activity_at"] is None or iso > row["last_activity_at"]:
            row["last_activity_at"] = iso

    for event in events:
        if not _in_range(event.created_at, start):
            continue
        if event.event_type == "tool_executed":
            totals["tool_calls"] += 1
            row = by_session.setdefault(
                event.session_id,
                {
                    "session_id": event.session_id,
                    **_empty_row_template(),
                    "tool_calls": 0,
                    "last_activity_at": None,
                },
            )
            row["tool_calls"] += 1
            iso = _as_utc(event.created_at).isoformat()
            if row["last_activity_at"] is None or iso > row["last_activity_at"]:
                row["last_activity_at"] = iso
            session_ids.add(event.session_id)
            continue

        if event.event_type != "model_call":
            continue

        payload = event.payload
        usage, req, resp, total = _call_usage(payload)
        model = _model_label(payload)
        cost = _call_cost(payload, model=model, usage=usage)
        day = _as_utc(event.created_at).date().isoformat()

        totals["input_tokens"] += req
        totals["output_tokens"] += resp
        totals["total_tokens"] += total
        totals["cost_usd"] = round(totals["cost_usd"] + cost, 6)
        totals["llm_calls"] += 1
        _bump_dimensions(totals, usage)
        session_ids.add(event.session_id)

        bump_daily(day, req, resp, total, cost, usage)
        bump_model(model, req, resp, total, cost, usage)
        bump_session(event.session_id, req, resp, total, cost, usage, event.created_at)

    totals["session_count"] = len(session_ids)

    daily_rows = sorted(daily.values(), key=lambda row: row["date"])
    model_rows = sorted(by_model.values(), key=lambda row: row["total_tokens"], reverse=True)
    session_rows = sorted(
        by_session.values(),
        key=lambda row: row["total_tokens"],
        reverse=True,
    )

    return {
        "range": range_key,
        "source": "trace",
        "totals": totals,
        "daily": daily_rows,
        "by_model": model_rows,
        "sessions": session_rows,
    }


def merge_session_metadata(
    usage: dict[str, Any],
    sessions: list[Session],
) -> dict[str, Any]:
    """Attach session titles and budget status; fill gaps from ``budget_usage``."""

    by_id = {session.id: session for session in sessions}
    trace_sessions = {
        row["session_id"]: row for row in usage.get("sessions", []) if isinstance(row, dict)
    }
    merged_rows: list[dict[str, Any]] = []

    for session_id, row in trace_sessions.items():
        session = by_id.get(session_id)
        merged_rows.append(
            {
                **row,
                "title": _session_title(session, session_id),
                "budget_status": session.budget_usage.last_budget_status if session else "ok",
            }
        )

    seen = set(trace_sessions)
    for session in sessions:
        if session.id in seen:
            continue
        budget = session.budget_usage
        if budget.llm_calls_total <= 0 and budget.tokens_total <= 0:
            continue
        merged_rows.append(
            {
                "session_id": session.id,
                "title": _session_title(session, session.id),
                "input_tokens": budget.tokens_total,
                "output_tokens": 0,
                "total_tokens": budget.tokens_total,
                "cost_usd": round(budget.cost_usd_total, 6),
                "llm_calls": budget.llm_calls_total,
                "tool_calls": budget.tool_calls_total,
                "dimensions": dict(_EMPTY_DIMENSIONS),
                "last_activity_at": (
                    session.last_step_at.isoformat() if session.last_step_at else None
                ),
                "budget_status": budget.last_budget_status,
            }
        )

    merged_rows.sort(key=lambda row: row.get("total_tokens", 0), reverse=True)
    usage = dict(usage)
    usage["sessions"] = merged_rows
    if usage["totals"]["llm_calls"] == 0:
        usage = _fallback_from_sessions(sessions, usage.get("range", "all"))
    return usage


def _session_title(session: Session | None, session_id: str) -> str:
    if session is None:
        return session_id
    if session.title and session.title.strip():
        return session.title.strip()
    if session.goal and session.goal.strip():
        goal = session.goal.strip()
        return goal if len(goal) <= 48 else f"{goal[:45]}…"
    return session_id


def _fallback_from_sessions(sessions: list[Session], range_key: str) -> dict[str, Any]:
    totals = {
        **_empty_row_template(),
        "tool_calls": 0,
        "session_count": 0,
    }
    rows: list[dict[str, Any]] = []
    for session in sessions:
        budget = session.budget_usage
        if budget.llm_calls_total <= 0 and budget.tokens_total <= 0:
            continue
        totals["input_tokens"] += budget.tokens_total
        totals["total_tokens"] += budget.tokens_total
        totals["cost_usd"] = round(totals["cost_usd"] + budget.cost_usd_total, 6)
        totals["llm_calls"] += budget.llm_calls_total
        totals["tool_calls"] += budget.tool_calls_total
        rows.append(
            {
                "session_id": session.id,
                "title": _session_title(session, session.id),
                "input_tokens": budget.tokens_total,
                "output_tokens": 0,
                "total_tokens": budget.tokens_total,
                "cost_usd": round(budget.cost_usd_total, 6),
                "llm_calls": budget.llm_calls_total,
                "tool_calls": budget.tool_calls_total,
                "dimensions": dict(_EMPTY_DIMENSIONS),
                "last_activity_at": (
                    session.last_step_at.isoformat() if session.last_step_at else None
                ),
                "budget_status": budget.last_budget_status,
            }
        )
    totals["session_count"] = len(rows)
    rows.sort(key=lambda row: row["total_tokens"], reverse=True)
    return {
        "range": range_key,
        "source": "sessions",
        "totals": totals,
        "daily": [],
        "by_model": [],
        "sessions": rows,
    }


def apply_usage_display_currency(
    usage: dict[str, Any],
    *,
    display_currency: str | None = None,
) -> dict[str, Any]:
    """Attach ``cost_display`` using catalog FX; budget ledger stays USD."""

    catalog = load_pricing_catalog()
    overrides = load_pricing_overrides()
    currency = (
        display_currency or overrides.display_currency or catalog.default_currency
    ).upper()
    symbols = currency_symbols_from_catalog(catalog.currencies)
    usd_per_unit_table = catalog.usd_per_unit

    def attach(row: dict[str, Any]) -> dict[str, Any]:
        cost_usd = row.get("cost_usd")
        if isinstance(cost_usd, (int, float)):
            row["cost_display"] = usd_to_display(
                float(cost_usd),
                display_currency=currency,
                usd_per_unit=usd_per_unit_table,
            )
        else:
            row["cost_display"] = None
        return row

    out = dict(usage)
    out["display_currency"] = currency
    out["currency_symbol"] = symbols.get(currency, currency)
    out["totals"] = attach(dict(out.get("totals", {})))
    out["daily"] = [attach(dict(row)) for row in out.get("daily", []) if isinstance(row, dict)]
    out["by_model"] = [
        attach(dict(row)) for row in out.get("by_model", []) if isinstance(row, dict)
    ]
    out["sessions"] = [
        attach(dict(row)) for row in out.get("sessions", []) if isinstance(row, dict)
    ]
    return out
