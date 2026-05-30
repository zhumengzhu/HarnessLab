"""Per-session steer queue for mid-turn user injection (Web UI)."""

from __future__ import annotations

import threading
from collections import deque


class TurnSteerBuffer:
    """Thread-safe FIFO of user messages to inject between inner-loop steps."""

    def __init__(self) -> None:
        self._queues: dict[str, deque[str]] = {}
        self._lock = threading.Lock()

    def push(self, session_id: str, message: str) -> int:
        """Append ``message``; return queue depth for ``session_id``."""

        text = message.strip()
        if not text:
            raise ValueError("message must not be empty")
        with self._lock:
            queue = self._queues.setdefault(session_id, deque())
            queue.append(text)
            return len(queue)

    def drain(self, session_id: str) -> list[str]:
        """Remove and return all pending steer messages for ``session_id``."""

        with self._lock:
            queue = self._queues.get(session_id)
            if not queue:
                return []
            items = list(queue)
            queue.clear()
            if not queue:
                self._queues.pop(session_id, None)
            return items

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._queues.pop(session_id, None)

    def pending_count(self, session_id: str) -> int:
        with self._lock:
            return len(self._queues.get(session_id, ()))
