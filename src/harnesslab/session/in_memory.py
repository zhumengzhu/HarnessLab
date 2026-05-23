from __future__ import annotations

from harnesslab.core.models import Session


class InMemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, Session] = {}

    def create(self, session: Session) -> None:
        self._data[session.id] = session

    def get(self, session_id: str) -> Session:
        return self._data[session_id]

    def save(self, session: Session) -> None:
        self._data[session.id] = session
