"""Shared helpers for Observability v2 span assertions in tests."""

from __future__ import annotations

from typing import Any

from harnesslab.core.models import SpanRecord
from harnesslab.telemetry.span_attributes import HARNESSLAB_COMPACTION_TRIGGER


def chronological_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return sorted(spans, key=lambda s: (s.start_time, s.span_id))


def span_events(
    spans: list[SpanRecord],
    event_name: str | None = None,
) -> list[tuple[SpanRecord, Any]]:
    rows: list[tuple[SpanRecord, Any]] = []
    for span in chronological_spans(spans):
        for event in span.events:
            if event_name is None or event.name == event_name:
                rows.append((span, event))
    return rows


def llm_generate_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return [s for s in chronological_spans(spans) if s.name == "llm.generate"]


def compact_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return [s for s in chronological_spans(spans) if s.name == "context.compact"]


def compact_trigger(span: SpanRecord) -> str | None:
    return span.attributes.get(HARNESSLAB_COMPACTION_TRIGGER)
