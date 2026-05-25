from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from harnesslab.core.models import ArtifactMeta
from harnesslab.storage.sqlite import apply_migrations, connect


class SqliteArtifactStore:
    """SQLite metadata + content-addressed files under ``.harnesslab/artifacts/``."""

    def __init__(self, db_path: Path, *, workspace_root: Path) -> None:
        self._db_path = Path(db_path)
        self._workspace_root = Path(workspace_root)
        self._artifacts_dir = self._workspace_root / ".harnesslab" / "artifacts"
        self._conn = connect(self._db_path)
        apply_migrations(self._conn)
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self._conn.close()

    def put(self, data: bytes, *, mime: str, session_id: str, artifact_id: str) -> str:
        digest = hashlib.sha256(data).hexdigest()
        rel_path = f"{digest[:16]}.bin"
        file_path = self._artifacts_dir / rel_path
        if not file_path.is_file():
            file_path.write_bytes(data)
        now = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO artifacts
                    (id, session_id, mime, size_bytes, sha256, storage_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, session_id, mime, len(data), digest, rel_path, now),
            )
        return artifact_id

    def get(self, ref: str) -> bytes:
        row = self._conn.execute(
            "SELECT storage_path FROM artifacts WHERE id = ?",
            (ref,),
        ).fetchone()
        if row is None:
            raise KeyError(f"artifact not found: {ref}")
        file_path = self._artifacts_dir / str(row["storage_path"])
        if not file_path.is_file():
            raise KeyError(f"artifact blob missing: {ref}")
        return file_path.read_bytes()

    def metadata(self, ref: str) -> ArtifactMeta:
        row = self._conn.execute(
            """
            SELECT id, session_id, mime, size_bytes, sha256, created_at
            FROM artifacts WHERE id = ?
            """,
            (ref,),
        ).fetchone()
        if row is None:
            raise KeyError(f"artifact not found: {ref}")
        return ArtifactMeta(
            id=str(row["id"]),
            session_id=str(row["session_id"]),
            mime=str(row["mime"]),
            size_bytes=int(row["size_bytes"]),
            sha256=str(row["sha256"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    def list(self, *, session_id: str | None = None, limit: int = 50) -> list[ArtifactMeta]:
        if session_id is None:
            rows = self._conn.execute(
                """
                SELECT id, session_id, mime, size_bytes, sha256, created_at
                FROM artifacts ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, session_id, mime, size_bytes, sha256, created_at
                FROM artifacts WHERE session_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            ArtifactMeta(
                id=str(r["id"]),
                session_id=str(r["session_id"]),
                mime=str(r["mime"]),
                size_bytes=int(r["size_bytes"]),
                sha256=str(r["sha256"]),
                created_at=datetime.fromisoformat(str(r["created_at"])),
            )
            for r in rows
        ]
