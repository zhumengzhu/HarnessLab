"""Replay stubs for Step 5.

These implementations are intentionally minimal:

- `ReplayModel` replays a fixed sequence of `Decision`s. It satisfies
  `ModelPort.decide` without ever calling an LLM, which is exactly what
  the Step-4 eval runner needs to compare a candidate against a frozen
  baseline of decisions.
- `ReplayTraceRecorder` collects `TraceEvent`s in memory instead of
  writing JSONL. It satisfies `TraceRecorderPort.record` and gives
  tests direct, ordered access to what the loop emitted.

The richer Step-5 replay machinery (loading historical decisions from
a JSONL trace, replaying with a `FrozenClock`, divergence detection)
will be built on top of these stubs.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from harnesslab.core.models import Decision, Session, TraceEvent


class ReplayModel:
    """A `ModelPort` that returns pre-recorded decisions in order."""

    def __init__(
        self,
        decisions: Iterable[Decision],
        exhausted_message: str = "(replay exhausted)",
    ) -> None:
        self._queue: deque[Decision] = deque(decisions)
        self._exhausted = Decision(kind="assistant", assistant_message=exhausted_message)

    def decide(self, session: Session, user_input: str) -> Decision:
        if not self._queue:
            return self._exhausted
        return self._queue.popleft()

    @property
    def remaining(self) -> int:
        return len(self._queue)


class ReplayTraceRecorder:
    """A `TraceRecorderPort` that appends events to an in-memory list."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(self, event: TraceEvent) -> None:
        self.events.append(event)

    def event_types(self) -> list[str]:
        return [e.event_type for e in self.events]
