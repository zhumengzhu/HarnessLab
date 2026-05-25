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

from harnesslab.telemetry.log import get_logger

_log = get_logger("storage.sqlite")

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
    (
        2,
        # Phase 2.3: first-class session lifecycle. ADD COLUMN with a
        # default applies retroactively to existing rows in SQLite, so
        # older sessions adopt step_count=0 and NULL for the new
        # optional fields.
        """
        ALTER TABLE sessions ADD COLUMN step_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE sessions ADD COLUMN last_step_at TEXT;
        ALTER TABLE sessions ADD COLUMN parent_session_id TEXT
            REFERENCES sessions(id);
        ALTER TABLE sessions ADD COLUMN title TEXT;

        CREATE INDEX IF NOT EXISTS idx_sessions_created_at
            ON sessions(created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_parent
            ON sessions(parent_session_id);
        """,
    ),
    (
        3,
        # Persist assistant tool_calls alongside tool result messages so
        # DeepSeek/OpenAI chat history round-trips correctly.
        """
        ALTER TABLE messages ADD COLUMN tool_calls TEXT;
        """,
    ),
    (
        4,
        # Post-MVP P1: optional reasoning / vendor round-trip fields on messages.
        """
        ALTER TABLE messages ADD COLUMN reasoning_text TEXT;
        ALTER TABLE messages ADD COLUMN provider_extra TEXT;
        """,
    ),
    (
        5,
        # Phase 5.10: session budget usage persistence.
        """
        ALTER TABLE sessions ADD COLUMN budget_usage TEXT;
        """,
    ),
    (
        6,
        # Phase 5.2: artifact metadata (blobs on disk under .harnesslab/artifacts/).
        """
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            mime TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_artifacts_session_created
            ON artifacts(session_id, created_at);
        """,
    ),
    (
        7,
        # Phase 5.9: session checkpoints before mutating tools.
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            tool_name TEXT NOT NULL,
            tool_args TEXT NOT NULL,
            snapshots TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_checkpoints_session_created
            ON checkpoints(session_id, created_at);
        """,
    ),
    (
        8,
        # Semantic memory retrieval (FTS5 keyword search PoC).
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS semantic_memory USING fts5(
            key UNINDEXED,
            text,
            metadata UNINDEXED,
            updated_at UNINDEXED,
            tokenize='porter'
        );
        """,
    ),
]


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key enforcement enabled.

    ``check_same_thread=False`` allows the Web UI server
    (``ThreadingHTTPServer``) to share one connection across worker
    threads. Callers must serialize writes (the web layer uses
    per-session locks; CLI is single-threaded).
    """

    conn = sqlite3.connect(str(path), check_same_thread=False)
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
        _log.info("applied sqlite migration version=%s", version)
        current = version
    return current


def current_version(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS v FROM schema_version;"
    )
    return int(cur.fetchone()["v"])
