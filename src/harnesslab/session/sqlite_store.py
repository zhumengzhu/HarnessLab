"""SQLite-backed SessionStorePort implementation.

`save` currently rewrites the message list wholesale inside a single
transaction. This is intentionally simple for Step 3; a more efficient
append-only variant is planned for Step 5 alongside the replay work.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from harnesslab.core.models import Message, Session
from harnesslab.storage.sqlite import apply_migrations, connect


class SqliteSessionStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn: sqlite3.Connection = connect(self._path)
        apply_migrations(self._conn)

    def close(self) -> None:
        self._conn.close()

    def create(self, session: Session) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO sessions(id, goal, status, turn_count, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    session.id,
                    session.goal,
                    session.status,
                    session.turn_count,
                    session.created_at.isoformat(),
                ),
            )
            self._insert_messages(session.id, session.messages)

    def get(self, session_id: str) -> Session:
        row = self._conn.execute(
            """
            SELECT id, goal, status, turn_count, created_at
            FROM sessions WHERE id = ?;
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        messages = self._load_messages(session_id)
        return Session(
            id=row["id"],
            goal=row["goal"],
            status=row["status"],
            turn_count=row["turn_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            messages=messages,
        )

    def save(self, session: Session) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO sessions(id, goal, status, turn_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    goal = excluded.goal,
                    status = excluded.status,
                    turn_count = excluded.turn_count,
                    created_at = excluded.created_at;
                """,
                (
                    session.id,
                    session.goal,
                    session.status,
                    session.turn_count,
                    session.created_at.isoformat(),
                ),
            )
            self._conn.execute(
                "DELETE FROM messages WHERE session_id = ?;",
                (session.id,),
            )
            self._insert_messages(session.id, session.messages)

    def _insert_messages(self, session_id: str, messages: list[Message]) -> None:
        if not messages:
            return
        self._conn.executemany(
            """
            INSERT INTO messages(
                id, session_id, role, content, created_at, tool_call_id, ord
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            [
                (
                    msg.id,
                    session_id,
                    msg.role,
                    msg.content,
                    msg.created_at.isoformat(),
                    msg.tool_call_id,
                    ord_,
                )
                for ord_, msg in enumerate(messages)
            ],
        )

    def _load_messages(self, session_id: str) -> list[Message]:
        rows = self._conn.execute(
            """
            SELECT id, role, content, created_at, tool_call_id
            FROM messages
            WHERE session_id = ?
            ORDER BY ord ASC;
            """,
            (session_id,),
        ).fetchall()
        return [
            Message(
                id=row["id"],
                role=row["role"],  # Pydantic validates against the Literal
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
                session_id=session_id,
                tool_call_id=row["tool_call_id"],
            )
            for row in rows
        ]
