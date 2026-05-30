"""Unit tests for context CLI span helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.cli import _collect_context_snapshots
from harnesslab.core.models import SpanRecord
from harnesslab.telemetry.span_attributes import SPAN_LLM_GENERATE


def _llm_span(
    *,
    session_id: str = "s_a",
    when: datetime | None = None,
    context: dict | None = None,
) -> SpanRecord:
    end = when or datetime.now(UTC)
    return SpanRecord(
        trace_id="t1",
        span_id="sp1",
        name=SPAN_LLM_GENERATE,
        session_id=session_id,
        turn_index=0,
        start_time=end,
        end_time=end,
        duration_ms=1.0,
        metrics={} if context is None else {"context": context},
    )


def test_collect_context_snapshots_filters_by_session_and_orders_by_time() -> None:
    base = datetime(2026, 5, 23, 10, 0, tzinfo=UTC)
    spans = [
        _llm_span(
            session_id="s_a",
            when=base,
            context={
                "conversation_tokens": 50,
                "message_count": 2,
                "limit_tokens": 1000,
                "compaction_threshold_tokens": 800,
                "usage_ratio": 0.05,
                "threshold_ratio": 0.0625,
            },
        ),
        _llm_span(
            session_id="s_b",
            when=base.replace(minute=1),
            context={
                "conversation_tokens": 99,
                "message_count": 3,
                "limit_tokens": 1000,
                "compaction_threshold_tokens": 800,
                "usage_ratio": 0.099,
                "threshold_ratio": 0.124,
            },
        ),
        _llm_span(
            session_id="s_a",
            when=base.replace(minute=2),
            context={
                "conversation_tokens": 75,
                "message_count": 4,
                "limit_tokens": 1000,
                "compaction_threshold_tokens": 800,
                "usage_ratio": 0.075,
                "threshold_ratio": 0.09375,
            },
        ),
    ]
    rows = _collect_context_snapshots(spans, session_id="s_a")
    assert [r["conversation_tokens"] for r in rows] == [50, 75]

    all_rows = _collect_context_snapshots(spans, session_id=None)
    assert len(all_rows) == 3
    assert all_rows == sorted(all_rows, key=lambda r: r["created_at"])


def test_collect_context_snapshots_skips_llm_without_context() -> None:
    spans = [
        _llm_span(context=None),
        _llm_span(
            context={
                "conversation_tokens": 5,
                "message_count": 1,
                "limit_tokens": 100,
                "compaction_threshold_tokens": 80,
                "usage_ratio": 0.05,
                "threshold_ratio": 0.0625,
            },
        ),
    ]
    rows = _collect_context_snapshots(spans, session_id=None)
    assert len(rows) == 1
    assert rows[0]["conversation_tokens"] == 5
