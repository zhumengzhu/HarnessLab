"""Session checkpoint snapshots before mutating tools (Phase 5.9)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harnesslab.storage.sqlite import apply_migrations, connect

MUTATING_TOOLS = frozenset({"write_file", "edit_file", "apply_patch"})


@dataclass(frozen=True)
class CheckpointMeta:
    id: str
    session_id: str
    tool_name: str
    created_at: datetime


@dataclass(frozen=True)
class Checkpoint:
    id: str
    session_id: str
    tool_name: str
    tool_args: dict[str, Any]
    snapshots: dict[str, str | None]
    created_at: datetime


class SqliteCheckpointStore:
    """Persist file snapshots keyed by checkpoint id."""

    def __init__(self, db_path: Path) -> None:
        self._conn = connect(db_path)
        apply_migrations(self._conn)

    def close(self) -> None:
        self._conn.close()

    def create(
        self,
        *,
        checkpoint_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        snapshots: dict[str, str | None],
    ) -> str:
        now = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO checkpoints
                    (id, session_id, tool_name, tool_args, snapshots, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    session_id,
                    tool_name,
                    json.dumps(tool_args),
                    json.dumps(snapshots),
                    now,
                ),
            )
        return checkpoint_id

    def get(self, checkpoint_id: str) -> Checkpoint:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE id = ?",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"checkpoint not found: {checkpoint_id}")
        return Checkpoint(
            id=str(row["id"]),
            session_id=str(row["session_id"]),
            tool_name=str(row["tool_name"]),
            tool_args=json.loads(str(row["tool_args"])),
            snapshots=json.loads(str(row["snapshots"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    def list(self, session_id: str, *, limit: int = 50) -> list[CheckpointMeta]:
        rows = self._conn.execute(
            """
            SELECT id, session_id, tool_name, created_at
            FROM checkpoints WHERE session_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [
            CheckpointMeta(
                id=str(r["id"]),
                session_id=str(r["session_id"]),
                tool_name=str(r["tool_name"]),
                created_at=datetime.fromisoformat(str(r["created_at"])),
            )
            for r in rows
        ]


def collect_file_snapshots(
    workspace_root: Path,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, str | None]:
    """Capture pre-mutation file contents for supported tools."""

    root = workspace_root.resolve()
    paths: list[Path] = []
    if tool_name == "write_file":
        rel = str(args.get("path", "")).strip()
        if rel:
            paths.append(root / rel)
    elif tool_name == "edit_file":
        rel = str(args.get("path", "")).strip()
        if rel:
            paths.append(root / rel)
    elif tool_name == "apply_patch":
        patch = str(args.get("patch", ""))
        for line in patch.splitlines():
            if line.startswith("+++ b/"):
                rel = line[6:].strip()
                if rel and rel != "/dev/null":
                    paths.append(root / rel)
            elif line.startswith("--- a/"):
                rel = line[6:].strip()
                if rel and rel != "/dev/null":
                    paths.append(root / rel)
    out: dict[str, str | None] = {}
    for path in paths:
        try:
            rel = path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if path.is_file():
            out[rel] = path.read_text(encoding="utf-8")
        else:
            out[rel] = None
    return out


def restore_snapshots(workspace_root: Path, snapshots: dict[str, str | None]) -> list[str]:
    """Restore files from a checkpoint. Returns relative paths touched."""

    root = workspace_root.resolve()
    touched: list[str] = []
    for rel, content in snapshots.items():
        path = root / rel
        if content is None:
            if path.is_file():
                path.unlink()
                touched.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        touched.append(rel)
    return touched
