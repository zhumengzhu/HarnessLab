"""SQLite-backed MemoryStorePort implementation.

The MVP `MemoryStorePort` is intentionally key/value. The richer
`MemoryRecord` model in `docs/architecture/data-model.md` is Planned
and will get its own table when it lands; the existing `memory_kv`
table stays untouched at that point.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from harnesslab.storage.sqlite import apply_migrations, connect


class SqliteMemoryStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn: sqlite3.Connection = connect(self._path)
        apply_migrations(self._conn)

    def close(self) -> None:
        self._conn.close()

    def put(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO memory_kv(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
                """,
                (key, value, datetime.now(UTC).isoformat()),
            )

    def get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM memory_kv WHERE key = ?;", (key,)
        ).fetchone()
        return None if row is None else str(row["value"])
