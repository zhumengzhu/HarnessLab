"""Read JSONL trace files into TraceEvent objects."""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

from harnesslab.core.models import TraceEvent


def read_trace(path: Path) -> list[TraceEvent]:
    """Parse a JSONL trace file into a list of TraceEvent.

    Blank lines are skipped. Each non-blank line must be a valid JSON
    object that validates against the TraceEvent schema; otherwise
    Pydantic raises a ValidationError, which we surface directly so the
    caller can decide how to react (replay should refuse to proceed).
    """

    events: list[TraceEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(TraceEvent.model_validate(json.loads(line)))
    return events


def group_by_session(events: list[TraceEvent]) -> dict[str, list[TraceEvent]]:
    """Group events by session_id, preserving the order they appeared in.

    Returns an OrderedDict so callers can iterate sessions in
    first-appearance order. Replaying a multi-session trace becomes
    ``for sid, evs in group_by_session(events).items(): replay(evs)``.
    """

    grouped: OrderedDict[str, list[TraceEvent]] = OrderedDict()
    for event in events:
        grouped.setdefault(event.session_id, []).append(event)
    return grouped
