"""HarnessLab replay subsystem (Observability v2).

Public API:
    read_spans(path)                  -> list[SpanRecord]
    group_by_session(spans)           -> dict[str, list[SpanRecord]]
    replay_session(spans)             -> list[SpanRecord]
    detect_divergence(orig, replayed) -> DivergenceReport
"""

from harnesslab.replay.replayer import UnreplayableTraceError, replay_session
from harnesslab.replay.span_divergence import (
    Divergence,
    DivergenceReport,
    detect_divergence,
)
from harnesslab.replay.span_reader import (
    child_session_ids_for_parent,
    filter_spans_by_session,
    group_by_session,
    read_spans,
)

__all__ = [
    "Divergence",
    "DivergenceReport",
    "UnreplayableTraceError",
    "child_session_ids_for_parent",
    "detect_divergence",
    "filter_spans_by_session",
    "group_by_session",
    "read_spans",
    "replay_session",
]
