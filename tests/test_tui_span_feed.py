"""Tests for TUI span feed formatter."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.core.models import SpanRecord
from harnesslab.tui.span_feed import SpanFeedFormatter


def _span(**kwargs: object) -> SpanRecord:
    base = {
        "span_id": "sp1",
        "trace_id": "tr1",
        "name": "tool.read_file",
        "session_id": "ses1",
        "turn_index": 0,
        "start_time": datetime(2026, 1, 1, tzinfo=UTC),
        "end_time": datetime(2026, 1, 1, tzinfo=UTC),
        "duration_ms": 10.0,
        "status": "ok",
        "attributes": {
            "harnesslab.session.id": "ses1",
            "harnesslab.tool.name": "read_file",
            "harnesslab.tool.ok": True,
        },
        "metrics": {"duration_ms": 12, "output_preview": "hello world"},
    }
    base.update(kwargs)
    return SpanRecord.model_validate(base)


def test_ingest_deduplicates_spans() -> None:
    feed = SpanFeedFormatter()
    span = _span()
    first = feed.ingest([span], session_id="ses1")
    second = feed.ingest([span], session_id="ses1")
    assert len(first) == 1
    assert "read_file" in first[0].plain
    assert second == []


def test_ingest_llm_generate_includes_tokens() -> None:
    feed = SpanFeedFormatter()
    span = _span(
        span_id="llm1",
        name="llm.generate",
        attributes={"harnesslab.session.id": "ses1"},
        metrics={"total_tokens": 120, "latency_ms": 800},
    )
    lines = feed.ingest([span], session_id="ses1")
    assert len(lines) == 1
    assert "120 tok" in lines[0].plain


def test_render_session_tree_indents_children() -> None:
    feed = SpanFeedFormatter()
    root = _span(
        span_id="root",
        name="harnesslab.turn",
        parent_span_id=None,
        attributes={"harnesslab.session.id": "ses1"},
    )
    child = _span(
        span_id="tool1",
        name="tool.read_file",
        parent_span_id="root",
        attributes={
            "harnesslab.session.id": "ses1",
            "harnesslab.tool.name": "read_file",
            "harnesslab.tool.ok": True,
        },
    )
    lines = feed.render_session_tree([root, child], session_id="ses1")
    plain = "\n".join(line.plain for line in lines)
    assert "── turn 0 ──" in plain
    assert "read_file" in plain
    assert "  ├─ tool read_file" in plain
