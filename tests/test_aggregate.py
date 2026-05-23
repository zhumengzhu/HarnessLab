"""Unit tests for telemetry.aggregate."""

from __future__ import annotations

import pytest

from harnesslab.core.models import TraceEvent
from harnesslab.telemetry.aggregate import (
    LatencyStats,
    aggregate,
    render_metrics,
)


def _evt(
    event_type: str,
    session: str = "ses_001",
    payload: dict | None = None,
) -> TraceEvent:
    return TraceEvent(
        run_id=session,
        session_id=session,
        event_type=event_type,
        payload=payload or {},
    )


# ---------- counts ----------


def test_aggregate_empty_trace_returns_zeros() -> None:
    m = aggregate([])
    assert m.sessions == 0
    assert m.turns == 0
    assert m.tool_calls == 0
    assert m.tool_success_rate is None
    assert m.denial_rate is None
    assert m.tool_latency is None
    assert m.model_calls == 0
    assert m.model_call_latency is None
    assert m.model_request_tokens == 0
    assert m.model_response_tokens == 0
    assert m.model_total_tokens == 0


def test_aggregate_counts_basic_events() -> None:
    events = [
        _evt("session_started"),
        _evt("user_input_received"),
        _evt(
            "model_call",
            payload={
                "latency_ms": 4.0,
                "request_tokens": 10,
                "response_tokens": 5,
                "total_tokens": 15,
            },
        ),
        _evt("decision_made"),
        _evt("tool_executed", payload={"ok": True, "duration_ms": 5.0}),
        _evt("user_input_received"),
        _evt("tool_denied"),
        _evt("user_input_received"),
        _evt("tool_invalid_args"),
    ]
    m = aggregate(events)
    assert m.sessions == 1
    assert m.turns == 3
    assert m.tool_calls == 1
    assert m.tool_successes == 1
    assert m.tool_failures == 0
    assert m.denials == 1
    assert m.invalid_args == 1
    assert m.model_calls == 1
    assert m.model_request_tokens == 10
    assert m.model_response_tokens == 5
    assert m.model_total_tokens == 15


def test_aggregate_counts_distinct_sessions() -> None:
    events = [_evt("user_input_received", session=f"ses_{i:03d}") for i in range(5)]
    assert aggregate(events).sessions == 5


# ---------- rates ----------


def test_tool_success_rate_with_mixed_outcomes() -> None:
    events = [
        _evt("tool_executed", payload={"ok": True, "duration_ms": 1.0}),
        _evt("tool_executed", payload={"ok": True, "duration_ms": 1.0}),
        _evt("tool_executed", payload={"ok": False, "duration_ms": 1.0}),
    ]
    m = aggregate(events)
    assert m.tool_calls == 3
    assert m.tool_successes == 2
    assert m.tool_failures == 1
    assert m.tool_success_rate == pytest.approx(2 / 3)


def test_denial_rate_uses_denials_plus_executions() -> None:
    events = [
        _evt("tool_executed", payload={"ok": True, "duration_ms": 1.0}),
        _evt("tool_executed", payload={"ok": True, "duration_ms": 1.0}),
        _evt("tool_executed", payload={"ok": True, "duration_ms": 1.0}),
        _evt("tool_denied"),
    ]
    m = aggregate(events)
    assert m.denial_rate == pytest.approx(0.25)


def test_rates_are_none_when_denominators_are_zero() -> None:
    events = [_evt("user_input_received"), _evt("decision_made")]
    m = aggregate(events)
    assert m.tool_success_rate is None
    assert m.denial_rate is None


# ---------- latency ----------


def test_latency_stats_single_sample() -> None:
    events = [_evt("tool_executed", payload={"ok": True, "duration_ms": 7.0})]
    lat = aggregate(events).tool_latency
    assert lat == LatencyStats(min_ms=7.0, p50_ms=7.0, p95_ms=7.0, max_ms=7.0, samples=1)


def test_latency_percentiles_match_linear_interpolation() -> None:
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    events = [
        _evt("tool_executed", payload={"ok": True, "duration_ms": v}) for v in samples
    ]
    lat = aggregate(events).tool_latency
    assert lat is not None
    assert lat.min_ms == 1.0
    assert lat.max_ms == 10.0
    assert lat.samples == 10
    assert lat.p50_ms == pytest.approx(5.5)
    assert lat.p95_ms == pytest.approx(9.55)


def test_latency_ignores_events_without_duration() -> None:
    events = [
        _evt("tool_executed", payload={"ok": True}),
        _evt("tool_executed", payload={"ok": True, "duration_ms": 3.0}),
    ]
    lat = aggregate(events).tool_latency
    assert lat is not None
    assert lat.samples == 1


# ---------- render ----------


def test_render_metrics_handles_zero_samples() -> None:
    out = render_metrics(aggregate([]))
    assert "sessions:        0" in out
    assert "tool_latency_ms: (no samples)" in out
    assert "model_latency_ms: (no samples)" in out
    assert "tool_success:    n/a" in out


def test_render_metrics_includes_percentiles() -> None:
    events = [
        _evt("tool_executed", payload={"ok": True, "duration_ms": 4.2}),
        _evt(
            "model_call",
            payload={
                "latency_ms": 8.1,
                "request_tokens": 100,
                "response_tokens": 20,
                "total_tokens": 120,
            },
        ),
    ]
    out = render_metrics(aggregate(events))
    assert "tool_success:    100.0%" in out
    assert "min=4.20 p50=4.20 p95=4.20 max=4.20 (n=1)" in out
    assert "model_tokens:    req=100 resp=20 total=120" in out
    assert "model_latency_ms: min=8.10 p50=8.10 p95=8.10 max=8.10 (n=1)" in out
