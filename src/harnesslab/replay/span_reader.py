"""Read JSONL span files into ``SpanRecord`` objects."""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

from harnesslab.core.models import SpanRecord


def read_spans(path: Path) -> list[SpanRecord]:
    """Parse a JSONL spans file into a list of ``SpanRecord``.

    Blank lines are skipped. Each non-blank line must validate as
    ``SpanRecord``; Pydantic errors propagate to the caller.
    """

    spans: list[SpanRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        spans.append(SpanRecord.model_validate(json.loads(line)))
    return spans


def filter_spans_by_session(
    spans: list[SpanRecord],
    session_id: str,
) -> list[SpanRecord]:
    """Return completed spans for ``session_id`` in JSONL read order."""

    return [span for span in spans if span.session_id == session_id]


def group_by_session(spans: list[SpanRecord]) -> dict[str, list[SpanRecord]]:
    """Group spans by ``session_id``, preserving first-appearance order."""

    grouped: OrderedDict[str, list[SpanRecord]] = OrderedDict()
    for span in spans:
        grouped.setdefault(span.session_id, []).append(span)
    return grouped


def child_session_ids_for_parent(
    spans: list[SpanRecord],
    parent_session_id: str,
) -> list[str]:
    """Return child session ids linked to ``parent_session_id``.

    Order follows first appearance in ``spans`` (``sub_agent.run`` attrs or
    turn root ``harnesslab.parent_session.id`` on child sessions).
    """

    ordered: OrderedDict[str, None] = OrderedDict()
    for span in spans:
        if span.name == "sub_agent.run" and span.session_id == parent_session_id:
            child_id = span.attributes.get("harnesslab.child_session.id")
            if isinstance(child_id, str) and child_id:
                ordered.setdefault(child_id, None)
        parent_id = span.attributes.get("harnesslab.parent_session.id")
        if parent_id == parent_session_id and span.name == "harnesslab.turn":
            ordered.setdefault(span.session_id, None)
    return list(ordered.keys())
