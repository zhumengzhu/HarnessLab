"""SQLite connection helpers and embedded schema migrations.

The migration set is intentionally kept as an in-process list of
``(version, sql)`` tuples to avoid shipping a separate ``migrations/``
directory at this stage. ``schema_version`` is still tracked in the
database so that future numbered migrations (Step 4+) can be applied
incrementally and idempotently.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            status TEXT NOT NULL,
            turn_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tool_call_id TEXT,
            ord INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session_ord
            ON messages(session_id, ord);

        CREATE TABLE IF NOT EXISTS memory_kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
]


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key enforcement enabled."""

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply every pending migration. Returns the new schema version."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """
    )
    cur = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version;")
    current = int(cur.fetchone()["v"])
    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES (?, ?);",
                (version, datetime.now(UTC).isoformat()),
            )
        current = version
    return current


def current_version(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS v FROM schema_version;"
    )
    return int(cur.fetchone()["v"])
