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


def test_verbose_tool_line_surfaces_error_and_artifact() -> None:
    feed = SpanFeedFormatter()
    span = _span(
        span_id="tool_err",
        name="tool.run_shell_safe",
        status="error",
        attributes={
            "harnesslab.session.id": "ses1",
            "harnesslab.tool.name": "run_shell_safe",
            "harnesslab.tool.ok": False,
        },
        metrics={
            "duration_ms": 5,
            "output_preview": "boom",
            "error": "command not in allowlist",
            "artifact_ref": "art_123",
        },
    )
    terse = "\n".join(
        line.markup for line in feed.render_session_tree([span], session_id="ses1")
    )
    assert "err:" not in terse
    assert "art_123" not in terse

    feed.reset()
    verbose = "\n".join(
        line.markup
        for line in feed.render_session_tree([span], session_id="ses1", verbose=True)
    )
    assert "err:" in verbose
    assert "command not in allowlist" in verbose
    assert "art_123" in verbose


def test_verbose_llm_line_includes_context_and_token_split() -> None:
    feed = SpanFeedFormatter()
    span = _span(
        span_id="llm_v",
        name="llm.generate",
        attributes={"harnesslab.session.id": "ses1"},
        metrics={
            "total_tokens": 300,
            "latency_ms": 900,
            "input_tokens": 220,
            "output_tokens": 80,
            "cost_usd": 0.0021,
            "context": {"conversation_tokens": 1500, "usage_ratio": 0.42},
        },
    )
    verbose = "\n".join(
        line.plain
        for line in feed.render_session_tree([span], session_id="ses1", verbose=True)
    )
    assert "in 220/out 80" in verbose
    assert "ctx 1500 tok (42%)" in verbose
