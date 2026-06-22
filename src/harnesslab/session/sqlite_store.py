"""SQLite-backed SessionStorePort implementation.

``save`` currently rewrites the message list wholesale inside a single
transaction. This is intentionally simple for Step 3; a more efficient
append-only variant is planned for Step 5 alongside the replay work.

Phase 2.3 added ``step_count``, ``last_step_at``, ``parent_session_id``,
and ``title``; the schema is bumped to version 2 via the embedded
migration in :mod:`harnesslab.storage.sqlite`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from harnesslab.core.models import BudgetUsage, Message, Session
from harnesslab.storage.sqlite import apply_migrations, connect

_SESSION_COLUMNS = (
    "id, goal, status, turn_count, step_count, created_at, "
    "last_step_at, parent_session_id, title, budget_usage, "
    "model_backend, model_id, model_effort"
)


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
                f"""
                INSERT INTO sessions({_SESSION_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                _session_row(session),
            )
            self._insert_messages(session.id, session.messages)

    def get(self, session_id: str) -> Session:
        row = self._conn.execute(
            f"""
            SELECT {_SESSION_COLUMNS}
            FROM sessions WHERE id = ?;
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        messages = self._load_messages(session_id)
        return _session_from_row(row, messages)

    def list(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        parent_session_id: str | None = None,
    ) -> list[Session]:
        # Sessions returned by ``list`` carry an empty messages list;
        # callers that need the conversation should call ``get`` for
        # the rows they actually want to display.
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if parent_session_id is not None:
            clauses.append("parent_session_id = ?")
            params.append(parent_session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"""
            SELECT {_SESSION_COLUMNS}
            FROM sessions
            {where}
            ORDER BY COALESCE(last_step_at, created_at) DESC
            LIMIT ?;
            """,
            tuple(params),
        ).fetchall()
        return [_session_from_row(r, messages=[]) for r in rows]

    def message_counts(self, session_ids: list[str]) -> dict[str, int]:
        if not session_ids:
            return {}
        placeholders = ",".join("?" * len(session_ids))
        rows = self._conn.execute(
            f"""
            SELECT session_id, COUNT(*) AS message_count
            FROM messages
            WHERE session_id IN ({placeholders})
            GROUP BY session_id;
            """,
            session_ids,
        ).fetchall()
        return {row["session_id"]: int(row["message_count"]) for row in rows}

    def save(self, session: Session) -> None:
        with self._conn:
            self._conn.execute(
                f"""
                INSERT INTO sessions({_SESSION_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    goal = excluded.goal,
                    status = excluded.status,
                    turn_count = excluded.turn_count,
                    step_count = excluded.step_count,
                    created_at = excluded.created_at,
                    last_step_at = excluded.last_step_at,
                    parent_session_id = excluded.parent_session_id,
                    title = excluded.title,
                    budget_usage = excluded.budget_usage,
                    model_backend = excluded.model_backend,
                    model_id = excluded.model_id,
                    model_effort = excluded.model_effort;
                """,
                _session_row(session),
            )
            self._conn.execute(
                "DELETE FROM messages WHERE session_id = ?;",
                (session.id,),
            )
            self._insert_messages(session.id, session.messages)

    def delete(self, session_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM messages WHERE session_id = ?;",
                (session_id,),
            )
            self._conn.execute(
                "DELETE FROM sessions WHERE id = ?;",
                (session_id,),
            )

    def _insert_messages(self, session_id: str, messages: list[Message]) -> None:
        if not messages:
            return
        self._conn.executemany(
            """
            INSERT INTO messages(
                id, session_id, role, content, created_at, tool_call_id,
                tool_calls, reasoning_text, provider_extra, ord
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            [
                (
                    msg.id,
                    session_id,
                    msg.role,
                    msg.content,
                    msg.created_at.isoformat(),
                    msg.tool_call_id,
                    _encode_tool_calls(msg.tool_calls),
                    msg.reasoning_text,
                    _encode_provider_extra(msg.provider_extra),
                    ord_,
                )
                for ord_, msg in enumerate(messages)
            ],
        )

    def _load_messages(self, session_id: str) -> list[Message]:
        rows = self._conn.execute(
            """
            SELECT id, role, content, created_at, tool_call_id, tool_calls,
                   reasoning_text, provider_extra
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
                tool_calls=_decode_tool_calls(row["tool_calls"]),
                reasoning_text=row["reasoning_text"],
                provider_extra=_decode_provider_extra(row["provider_extra"]),
            )
            for row in rows
        ]


def _session_row(session: Session) -> tuple:
    return (
        session.id,
        session.goal,
        session.status,
        session.turn_count,
        session.step_count,
        session.created_at.isoformat(),
        session.last_step_at.isoformat() if session.last_step_at else None,
        session.parent_session_id,
        session.title,
        _encode_budget_usage(session.budget_usage),
        session.model_backend,
        session.model_id,
        session.model_effort,
    )


def _session_from_row(row: sqlite3.Row, messages: list[Message]) -> Session:
    last_step_at_raw = row["last_step_at"]
    return Session(
        id=row["id"],
        goal=row["goal"],
        status=row["status"],
        turn_count=row["turn_count"],
        step_count=row["step_count"],
        created_at=datetime.fromisoformat(row["created_at"]),
        last_step_at=(
            datetime.fromisoformat(last_step_at_raw) if last_step_at_raw else None
        ),
        parent_session_id=row["parent_session_id"],
        title=row["title"],
        budget_usage=_decode_budget_usage(row["budget_usage"]),
        model_backend=row["model_backend"],
        model_id=row["model_id"],
        model_effort=row["model_effort"],
        messages=messages,
    )


def _encode_tool_calls(tool_calls: list[dict] | None) -> str | None:
    if not tool_calls:
        return None
    return json.dumps(tool_calls, ensure_ascii=False)


def _decode_tool_calls(raw: str | None) -> list[dict] | None:
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        return None
    return parsed


def _encode_provider_extra(provider_extra: dict | None) -> str | None:
    if not provider_extra:
        return None
    return json.dumps(provider_extra, ensure_ascii=False)


def _decode_provider_extra(raw: str | None) -> dict | None:
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return None
    return parsed


def _encode_budget_usage(usage: BudgetUsage) -> str:
    return json.dumps(usage.model_dump(mode="json"), ensure_ascii=False)


def _decode_budget_usage(raw: str | None) -> BudgetUsage:
    if not raw:
        return BudgetUsage()
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return BudgetUsage()
    return BudgetUsage.model_validate(parsed)
