"""Fan-out trace recorder with live subscribers (Web UI SSE)."""

from __future__ import annotations

import threading
from collections.abc import Callable

from harnesslab.core.contracts import TraceRecorderPort
from harnesslab.core.models import TraceEvent

TraceListener = Callable[[TraceEvent], None]


class TraceHub:
    """Record to an inner port and notify ephemeral subscribers."""

    def __init__(self, inner: TraceRecorderPort) -> None:
        self._inner = inner
        self._listeners: list[TraceListener] = []
        self._lock = threading.Lock()

    def record(self, event: TraceEvent) -> None:
        self._inner.record(event)
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener(event)

    def subscribe(self, listener: TraceListener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def unsubscribe(self, listener: TraceListener) -> None:
        with self._lock:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass
