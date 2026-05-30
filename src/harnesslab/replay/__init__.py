"""HarnessLab replay subsystem (Step 5).

Public API:
    read_trace(path)                  -> list[TraceEvent]
    group_by_session(events)          -> dict[str, list[TraceEvent]]
    replay_session(events)            -> list[TraceEvent]
    detect_divergence(orig, replayed) -> DivergenceReport
"""

from harnesslab.replay.divergence import (
    Divergence,
    DivergenceReport,
    detect_divergence,
)
from harnesslab.replay.replayer import UnreplayableTraceError, replay_session
from harnesslab.replay.trace_reader import (
    child_session_ids_for_parent,
    group_by_session,
    read_trace,
)

__all__ = [
    "Divergence",
    "DivergenceReport",
    "UnreplayableTraceError",
    "child_session_ids_for_parent",
    "detect_divergence",
    "group_by_session",
    "read_trace",
    "replay_session",
]
