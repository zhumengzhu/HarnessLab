"""Usage aggregation from trace events."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.core.models import TraceEvent
from harnesslab.web.usage_aggregate import (
    aggregate_usage_from_events,
    apply_usage_display_currency,
    usage_range_start,
)


def _model_call(
    *,
    session_id: str = "sess_a",
    created_at: datetime,
    request_tokens: int = 100,
    response_tokens: int = 50,
    model_name: str = "deepseek-v4-flash",
) -> TraceEvent:
    return TraceEvent(
        run_id="run_1",
        session_id=session_id,
        event_type="model_call",
        created_at=created_at,
        payload={
            "model_name": model_name,
            "request_tokens": request_tokens,
            "response_tokens": response_tokens,
            "total_tokens": request_tokens + response_tokens,
        },
    )


def test_aggregate_usage_groups_by_day_and_model() -> None:
    now = datetime(2026, 5, 30, 18, 0, tzinfo=UTC)
    events = [
        _model_call(
            created_at=datetime(2026, 5, 30, 10, 0, tzinfo=UTC),
            request_tokens=73600,
            response_tokens=6700,
        ),
        _model_call(
            created_at=datetime(2026, 5, 29, 9, 0, tzinfo=UTC),
            request_tokens=1000,
            response_tokens=200,
            model_name="gpt-5-mini",
        ),
    ]
    result = aggregate_usage_from_events(events, range_key="all", now=now)

    assert result["totals"]["input_tokens"] == 74600
    assert result["totals"]["output_tokens"] == 6900
    assert result["totals"]["total_tokens"] == 81500
    assert result["totals"]["llm_calls"] == 2
    assert len(result["daily"]) == 2
    assert result["daily"][-1]["date"] == "2026-05-30"
    assert result["daily"][-1]["input_tokens"] == 73600
    assert len(result["by_model"]) == 2
    assert result["by_model"][0]["model"] == "deepseek-v4-flash"
    assert result["sessions"][0]["session_id"] == "sess_a"


def test_aggregate_usage_respects_range() -> None:
    now = datetime(2026, 5, 30, 18, 0, tzinfo=UTC)
    events = [
        _model_call(created_at=datetime(2026, 5, 30, 10, 0, tzinfo=UTC)),
        _model_call(created_at=datetime(2026, 5, 20, 10, 0, tzinfo=UTC)),
    ]
    result = aggregate_usage_from_events(events, range_key="7d", now=now)
    assert result["totals"]["llm_calls"] == 1


def test_aggregate_usage_prefers_breakdown_and_cost_estimate() -> None:
    now = datetime(2026, 5, 30, 18, 0, tzinfo=UTC)
    event = TraceEvent(
        run_id="run_1",
        session_id="sess_a",
        event_type="model_call",
        created_at=now,
        payload={
            "model_name": "deepseek-v4-flash",
            "request_tokens": 500,
            "response_tokens": 100,
            "usage_breakdown": {
                "input": 200,
                "output": 100,
                "cache_read": 300,
            },
            "cost_estimate": {
                "amount_usd": 0.123456,
                "status": "estimated",
                "source": "catalog",
            },
        },
    )
    result = aggregate_usage_from_events([event], range_key="all", now=now)
    assert result["totals"]["input_tokens"] == 500
    assert result["totals"]["output_tokens"] == 100
    assert result["totals"]["cost_usd"] == 0.123456
    assert result["totals"]["dimensions"]["cache_read"] == 300
    assert result["totals"]["dimensions"]["input"] == 200


def test_apply_usage_display_currency_adds_cost_display() -> None:
    usage = {
        "range": "all",
        "source": "trace",
        "totals": {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "cost_usd": 1.4,
            "llm_calls": 1,
            "tool_calls": 0,
            "session_count": 1,
            "dimensions": {},
        },
        "daily": [],
        "by_model": [],
        "sessions": [],
    }
    out = apply_usage_display_currency(usage, display_currency="CNY")
    assert out["display_currency"] == "CNY"
    assert out["currency_symbol"] == "¥"
    assert out["totals"]["cost_display"] == 10.0


def test_usage_range_start_today() -> None:
    now = datetime(2026, 5, 30, 18, 30, tzinfo=UTC)
    start = usage_range_start("today", now)
    assert start is not None
    assert start.hour == 0
    assert start.day == 30
