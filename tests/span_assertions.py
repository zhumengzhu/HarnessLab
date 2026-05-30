"""Helpers for asserting Observability v2 span output in tests."""

from __future__ import annotations

import json
from pathlib import Path

from harnesslab.core.models import SpanRecord
from harnesslab.telemetry.span_attributes import (
    HARNESSLAB_STEPS_USED,
    HARNESSLAB_TERMINAL_REASON,
    SPAN_STEP,
    SPAN_TURN,
)


def read_spans_jsonl(workspace_root: Path) -> list[dict]:
    path = workspace_root / ".harnesslab" / "spans.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def read_span_records(path: Path) -> list[SpanRecord]:
    if not path.is_file():
        return []
    rows: list[SpanRecord] = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(SpanRecord.model_validate(json.loads(line)))
    return rows


def turn_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return [s for s in spans if s.name == SPAN_TURN]


def step_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return [s for s in spans if s.name == SPAN_STEP]


def llm_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return [s for s in spans if s.name == "llm.generate"]


def tool_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return [s for s in spans if s.name.startswith("tool.") and not s.name.startswith("tool.hooks.")]


def compact_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return [s for s in spans if s.name == "context.compact"]


def span_events(
    spans: list[SpanRecord], event_name: str
) -> list[tuple[SpanRecord, dict]]:
    found: list[tuple[SpanRecord, dict]] = []
    for span in spans:
        for event in span.events:
            if event.name == event_name:
                found.append((span, event.attributes))
    return found


def last_turn(spans: list[SpanRecord]) -> SpanRecord:
    turns = turn_spans(spans)
    assert turns, "expected at least one harnesslab.turn span"
    return turns[-1]


def turn_terminal(turn: SpanRecord) -> tuple[str, int]:
    reason = turn.attributes.get(HARNESSLAB_TERMINAL_REASON)
    steps = turn.attributes.get(HARNESSLAB_STEPS_USED)
    assert reason is not None
    assert steps is not None
    return str(reason), int(steps)
