"""Replay stubs for Step 5.

These implementations are intentionally minimal:

- `ReplayModel` replays a fixed sequence of `Decision`s. It satisfies
  `ModelPort.decide` without ever calling an LLM, which is exactly what
  the Step-4 eval runner needs to compare a candidate against a frozen
  baseline of decisions.
- `ReplaySpanRecorder` collects completed `SpanRecord`s in memory for
  tests and eval replay.

The Step-5 replay machinery (loading historical spans, replaying with
a `FrozenClock`, divergence detection) builds on these stubs.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from harnesslab.core.models import Decision, Session, SpanRecord
from harnesslab.telemetry.memory_span_recorder import MemorySpanRecorder


class ReplayModel:
    """A `ModelPort` that returns pre-recorded decisions in order."""

    def __init__(
        self,
        decisions: Iterable[Decision],
        exhausted_message: str = "(replay exhausted)",
        *,
        call_meta: dict[str, object] | None = None,
    ) -> None:
        self._queue: deque[Decision] = deque(decisions)
        self._exhausted = Decision(kind="assistant", assistant_message=exhausted_message)
        self._call_meta = dict(call_meta or {})
        self._last_call_meta: dict[str, object] = dict(self._call_meta)

    def decide(self, session: Session, user_input: str) -> Decision:
        if not self._queue:
            return self._exhausted
        self._last_call_meta = dict(self._call_meta)
        return self._queue.popleft()

    def last_call_meta(self) -> dict[str, object]:
        return dict(self._last_call_meta)

    @property
    def remaining(self) -> int:
        return len(self._queue)


class ReplaySpanRecorder(MemorySpanRecorder):
    """Collect completed ``SpanRecord`` rows in memory (Observability v2)."""

    @property
    def spans(self) -> list[SpanRecord]:
        return list(self._completed)
