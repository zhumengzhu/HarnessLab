"""Tests for cli.build_runtime storage backend selection."""

from __future__ import annotations

from pathlib import Path

from harnesslab.cli import DEFAULT_SQLITE_PATH, build_runtime
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.session.sqlite_store import SqliteSessionStore


def test_build_runtime_defaults_to_memory(tmp_path: Path) -> None:
    loop = build_runtime(workspace_root=tmp_path)
    # We deliberately keep the loop's internals private; reach in only for the
    # backend assertion since "default backend" is part of the CLI contract.
    assert isinstance(loop._sessions, InMemorySessionStore)  # type: ignore[attr-defined]
    assert not (tmp_path / DEFAULT_SQLITE_PATH).exists()


def test_build_runtime_sqlite_creates_default_path(tmp_path: Path) -> None:
    loop = build_runtime(workspace_root=tmp_path, storage_backend="sqlite")
    assert isinstance(loop._sessions, SqliteSessionStore)  # type: ignore[attr-defined]
    assert (tmp_path / DEFAULT_SQLITE_PATH).exists()


def test_build_runtime_sqlite_with_relative_custom_path(tmp_path: Path) -> None:
    loop = build_runtime(
        workspace_root=tmp_path,
        storage_backend="sqlite",
        sqlite_path=Path("alt/state.sqlite"),
    )
    assert isinstance(loop._sessions, SqliteSessionStore)  # type: ignore[attr-defined]
    assert (tmp_path / "alt" / "state.sqlite").exists()


def test_session_persists_via_cli_with_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "alt" / "shared.sqlite"

    loop1 = build_runtime(
        workspace_root=tmp_path,
        storage_backend="sqlite",
        sqlite_path=db,
    )
    session = loop1.start(goal="durable")
    loop1.run_turn(session.id, "hello")
    loop1._sessions.close()  # type: ignore[attr-defined]

    loop2 = build_runtime(
        workspace_root=tmp_path,
        storage_backend="sqlite",
        sqlite_path=db,
    )
    loaded = loop2._sessions.get(session.id)  # type: ignore[attr-defined]
    assert loaded.goal == "durable"
    assert len(loaded.messages) >= 1
    loop2._sessions.close()  # type: ignore[attr-defined]
