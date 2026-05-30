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

    def list(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        parent_session_id: str | None = None,
    ) -> list[Session]:
        sessions = sorted(
            self._data.values(),
            key=lambda s: s.last_step_at or s.created_at,
            reverse=True,
        )
        if status is not None:
            sessions = [s for s in sessions if s.status == status]
        if parent_session_id is not None:
            sessions = [
                s for s in sessions if s.parent_session_id == parent_session_id
            ]
        return sessions[:limit]

    def message_counts(self, session_ids: list[str]) -> dict[str, int]:
        return {
            session_id: len(self._data[session_id].messages)
            for session_id in session_ids
            if session_id in self._data
        }
