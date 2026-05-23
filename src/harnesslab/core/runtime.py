"""Built-in implementations of `ClockPort` and `IdPort`.

Two flavors are shipped:

- `SystemClock` / `UuidIdProvider` — production defaults; non-deterministic.
- `FrozenClock` / `SeqIdProvider`  — deterministic; used by the eval
  runner (Step 4) and the replayer (Step 5) so traces are byte-stable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import uuid4


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidIdProvider:
    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:12]}"


class FrozenClock:
    """Advances `step` on every call; deterministic across processes.

    Default step is 1ms, which keeps `tool_executed.duration_ms` at 1.0
    for the close-paired (start, end) measurements taken by HarnessLoop
    around tool execution.
    """

    def __init__(
        self,
        start: datetime,
        step: timedelta = timedelta(milliseconds=1),
    ) -> None:
        self._t = start
        self._step = step

    def now(self) -> datetime:
        current = self._t
        self._t = self._t + self._step
        return current


class SeqIdProvider:
    """Generates monotonically increasing ids per-prefix: ses_000001, …"""

    def __init__(self) -> None:
        self._counters: dict[str, count[int]] = {}

    def new_id(self, prefix: str) -> str:
        if prefix not in self._counters:
            self._counters[prefix] = count(1)
        return f"{prefix}_{next(self._counters[prefix]):06d}"


DEFAULT_REPLAY_CLOCK_START = datetime(2026, 1, 1, tzinfo=UTC)
