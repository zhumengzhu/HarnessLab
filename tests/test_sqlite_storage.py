"""SQLite-specific tests: migrations, message round-trip, persistence."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.models import Message, Session
from harnesslab.memory.sqlite_store import SqliteMemoryStore
from harnesslab.session.sqlite_store import SqliteSessionStore
from harnesslab.storage.sqlite import (
    MIGRATIONS,
    apply_migrations,
    connect,
    current_version,
)


def test_apply_migrations_creates_expected_tables(tmp_path: Path) -> None:
    conn = connect(tmp_path / "x.sqlite")
    try:
        apply_migrations(conn)
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
        for required in {"schema_version", "sessions", "messages", "memory_kv"}:
            assert required in names, required
    finally:
        conn.close()


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "x.sqlite"
    conn1 = connect(db)
    try:
        v1 = apply_migrations(conn1)
        v2 = apply_migrations(conn1)
        assert v1 == v2 == MIGRATIONS[-1][0]
        rows = conn1.execute("SELECT COUNT(*) AS c FROM schema_version;").fetchone()
        # Each shipped migration writes exactly one row; re-running
        # apply_migrations must not duplicate those rows.
        assert rows["c"] == len(MIGRATIONS), "migration applied twice"
    finally:
        conn1.close()


def test_current_version_reflects_latest_migration(tmp_path: Path) -> None:
    conn = connect(tmp_path / "x.sqlite")
    try:
        apply_migrations(conn)
        assert current_version(conn) == MIGRATIONS[-1][0]
    finally:
        conn.close()


def test_session_round_trip_preserves_messages(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.sqlite")
    try:
        session = Session(goal="round trip with messages")
        session.messages.append(
            Message(role="user", content="hi", session_id=session.id)
        )
        session.messages.append(
            Message(
                role="tool",
                content="[tool:write_file] ok",
                session_id=session.id,
                tool_call_id="tool_abc",
            )
        )
        session.turn_count = 1
        store.create(session)

        loaded = store.get(session.id)
        assert loaded.id == session.id
        assert loaded.goal == session.goal
        assert loaded.turn_count == 1
        assert [m.role for m in loaded.messages] == ["user", "tool"]
        assert loaded.messages[1].tool_call_id == "tool_abc"
        assert loaded.messages[0].session_id == session.id
    finally:
        store.close()


def test_session_save_rewrites_messages(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.sqlite")
    try:
        session = Session(goal="rewrite")
        session.messages.append(Message(role="user", content="first"))
        store.create(session)

        session.messages.append(Message(role="assistant", content="second"))
        session.turn_count = 1
        store.save(session)

        loaded = store.get(session.id)
        assert [m.content for m in loaded.messages] == ["first", "second"]
        assert loaded.turn_count == 1
    finally:
        store.close()


def test_session_persists_across_store_instances(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"

    store1 = SqliteSessionStore(db)
    session = Session(goal="persist")
    store1.create(session)
    store1.close()

    store2 = SqliteSessionStore(db)
    try:
        loaded = store2.get(session.id)
        assert loaded.id == session.id
        assert loaded.goal == "persist"
    finally:
        store2.close()


def test_memory_persists_across_store_instances(tmp_path: Path) -> None:
    db = tmp_path / "m.sqlite"

    store1 = SqliteMemoryStore(db)
    store1.put("k", "v1")
    store1.put("k", "v2")
    store1.close()

    store2 = SqliteMemoryStore(db)
    try:
        assert store2.get("k") == "v2"
        assert store2.get("missing") is None
    finally:
        store2.close()
