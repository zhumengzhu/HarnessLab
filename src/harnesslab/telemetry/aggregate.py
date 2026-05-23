"""Aggregate metrics from a list of TraceEvent.

This module is intentionally pure (no IO): hand it events, it returns
a Metrics object. The CLI and any future telemetry sink wrap it.

What's measured (Step 5 scope):
  - session count (distinct session_id)
  - turn count (user_input_received events)
  - tool_calls, tool_successes, tool_failures (tool_executed events)
  - denials (tool_denied events)
  - invalid_args (tool_invalid_args events)
  - tool_success_rate, denial_rate (None when denominators are zero)
  - tool_latency: min / p50 / p95 / max from tool_executed.duration_ms

What's intentionally NOT measured: "session pass rate". Production
sessions have no built-in pass/fail signal; that lives in the eval
suite and is reported by `harnesslab eval`.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from harnesslab.core.models import TraceEvent


class LatencyStats(BaseModel):
    min_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    samples: int


class Metrics(BaseModel):
    sessions: int
    turns: int
    tool_calls: int
    tool_successes: int
    tool_failures: int
    denials: int
    invalid_args: int
    tool_success_rate: float | None
    denial_rate: float | None
    tool_latency: LatencyStats | None


def aggregate(events: list[TraceEvent]) -> Metrics:
    sessions = {e.session_id for e in events}
    turns = sum(1 for e in events if e.event_type == "user_input_received")

    tool_calls = 0
    tool_successes = 0
    tool_failures = 0
    latencies: list[float] = []

    for e in events:
        if e.event_type != "tool_executed":
            continue
        tool_calls += 1
        if e.payload.get("ok"):
            tool_successes += 1
        else:
            tool_failures += 1
        dur = e.payload.get("duration_ms")
        if isinstance(dur, int | float):
            latencies.append(float(dur))

    denials = sum(1 for e in events if e.event_type == "tool_denied")
    invalid_args = sum(1 for e in events if e.event_type == "tool_invalid_args")

    return Metrics(
        sessions=len(sessions),
        turns=turns,
        tool_calls=tool_calls,
        tool_successes=tool_successes,
        tool_failures=tool_failures,
        denials=denials,
        invalid_args=invalid_args,
        tool_success_rate=(tool_successes / tool_calls) if tool_calls else None,
        denial_rate=(
            denials / (denials + tool_calls) if (denials + tool_calls) else None
        ),
        tool_latency=_latency_stats(latencies),
    )


def _latency_stats(samples: list[float]) -> LatencyStats | None:
    if not samples:
        return None
    return LatencyStats(
        min_ms=min(samples),
        p50_ms=_percentile(samples, 50),
        p95_ms=_percentile(samples, 95),
        max_ms=max(samples),
        samples=len(samples),
    )


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (NIST 7.2.5.2). Matches numpy's
    default ``linear`` method, but stdlib-only so we don't pull numpy
    into a learning-focused project for one stat."""

    if not values:
        raise ValueError("percentile of empty list")
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def render_metrics(metrics: Metrics) -> str:
    """Human-readable single-block view; useful as a CLI default."""
    lines = [
        "Metrics:",
        f"  sessions:        {metrics.sessions}",
        f"  turns:           {metrics.turns}",
        f"  tool_calls:      {metrics.tool_calls}",
        f"  tool_successes:  {metrics.tool_successes}",
        f"  tool_failures:   {metrics.tool_failures}",
        f"  denials:         {metrics.denials}",
        f"  invalid_args:    {metrics.invalid_args}",
        f"  tool_success:    {_fmt_rate(metrics.tool_success_rate)}",
        f"  denial_rate:     {_fmt_rate(metrics.denial_rate)}",
    ]
    if metrics.tool_latency:
        lat = metrics.tool_latency
        lines.append(
            "  tool_latency_ms: "
            f"min={lat.min_ms:.2f} p50={lat.p50_ms:.2f} "
            f"p95={lat.p95_ms:.2f} max={lat.max_ms:.2f} "
            f"(n={lat.samples})"
        )
    else:
        lines.append("  tool_latency_ms: (no samples)")
    return "\n".join(lines)


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
