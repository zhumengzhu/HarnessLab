"""SQLite FTS5 semantic memory store (deferred RAG PoC)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from harnesslab.storage.sqlite import apply_migrations, connect


@dataclass(frozen=True)
class SemanticHit:
    key: str
    text: str
    score: float


class SqliteSemanticMemoryStore:
    """Keyword retrieval via FTS5 (explicit upsert; no auto-write)."""

    def __init__(self, db_path) -> None:
        self._conn = connect(db_path)
        apply_migrations(self._conn)

    def close(self) -> None:
        self._conn.close()

    def upsert(self, key: str, text: str, metadata: dict | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        meta_json = "" if metadata is None else __import__("json").dumps(metadata)
        with self._conn:
            self._conn.execute(
                "DELETE FROM semantic_memory WHERE key = ?",
                (key,),
            )
            self._conn.execute(
                """
                INSERT INTO semantic_memory(key, text, metadata, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, text, meta_json, now),
            )

    def search(self, query: str, k: int = 5) -> list[SemanticHit]:
        rows = self._conn.execute(
            """
            SELECT key, text, bm25(semantic_memory) AS score
            FROM semantic_memory
            WHERE semantic_memory MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (query, k),
        ).fetchall()
        return [
            SemanticHit(key=str(r["key"]), text=str(r["text"]), score=float(r["score"]))
            for r in rows
        ]

    def get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT text FROM semantic_memory WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["text"]) if row else None
