"""Phase 2.3 commit 1: session-as-first-class-citizen.

Covers:

- :class:`Session` carries the new lifecycle fields with sensible defaults.
- :class:`HarnessLoop` populates ``step_count``, ``last_step_at``,
  ``status``, and ``title``; ``fork`` copies messages and pins the
  parent id.
- :class:`SqliteSessionStore` round-trips the new fields, and the
  v2 migration upgrades an existing v1 database in place.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from harnesslab.cli import build_runtime
from harnesslab.core.models import Decision, Message, Session
from harnesslab.session.sqlite_store import SqliteSessionStore
from harnesslab.storage.sqlite import apply_migrations, connect, current_version

# ---------- model defaults ----------


def test_session_defaults_include_new_lifecycle_fields() -> None:
    s = Session(goal="probe")
    assert s.status == "running"
    assert s.turn_count == 0
    assert s.step_count == 0
    assert s.last_step_at is None
    assert s.parent_session_id is None
    assert s.title is None


# ---------- loop populates the new fields ----------


def test_run_session_updates_step_count_and_last_step_at(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="track steps")
    assert session.title == "track steps"

    loop.run_session(session.id, "/final all set", max_steps=5)

    refreshed = loop._sessions.get(session.id)  # type: ignore[attr-defined]
    assert refreshed.step_count == 1
    assert refreshed.last_step_at is not None
    assert refreshed.turn_count == 1
    assert refreshed.status == "done"


def test_run_session_status_waiting_user_on_ask(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="ask flow")
    loop.run_session(session.id, "/ask what next?", max_steps=3)

    refreshed = loop._sessions.get(session.id)  # type: ignore[attr-defined]
    assert refreshed.status == "waiting_user"


def test_run_session_status_running_on_max_steps(tmp_path: Path) -> None:
    """A truncation by max_steps leaves the session resumable."""
    loop = build_runtime(tmp_path)
    session = loop.start(goal="runaway")
    loop.run_session(
        session.id,
        '/tool write_file {"path":"a.txt","content":"x"}',
        max_steps=1,
    )

    refreshed = loop._sessions.get(session.id)  # type: ignore[attr-defined]
    assert refreshed.status == "running"
    assert refreshed.step_count == 1


def test_run_session_status_resets_to_running_on_new_input(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="resume after done")
    loop.run_session(session.id, "/final first answer", max_steps=2)
    first = loop._sessions.get(session.id)  # type: ignore[attr-defined]
    assert first.status == "done"

    loop.run_session(session.id, "/final follow-up", max_steps=2)
    after = loop._sessions.get(session.id)  # type: ignore[attr-defined]
    assert after.status == "done"
    assert after.turn_count == 2
    assert after.step_count == 2


# ---------- title derivation ----------


def test_loop_start_sets_title_from_short_goal(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="ship the changelog")
    assert session.title == "ship the changelog"


def test_loop_start_truncates_long_goal_into_title(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    long_goal = "x" * 200
    session = loop.start(goal=long_goal)
    assert session.title is not None
    assert len(session.title) <= 60
    assert session.title.endswith("…")


def test_loop_start_handles_empty_goal(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="")
    assert session.title == "(no title)"


def test_loop_start_uses_first_nonblank_line_for_title(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="\n   \nactual goal\nmore body\n")
    assert session.title == "actual goal"


# ---------- fork ----------


def test_loop_fork_copies_messages_and_pins_parent(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    parent = loop.start(goal="parent task")
    loop.run_session(parent.id, "/final parent done", max_steps=2)

    forked = loop.fork(parent.id, goal="fork experiment")

    assert forked.id != parent.id
    assert forked.parent_session_id == parent.id
    assert forked.title == "fork experiment"
    assert forked.status == "running"
    # Parent's messages copied by value.
    parent_after = loop._sessions.get(parent.id)  # type: ignore[attr-defined]
    assert [m.content for m in forked.messages] == [
        m.content for m in parent_after.messages
    ]
    forked.messages.append(
        Message(
            id="msg_extra",
            role="user",
            content="fork-only",
            created_at=datetime(2026, 5, 23, tzinfo=UTC),
            session_id=forked.id,
        )
    )
    assert len(parent_after.messages) != len(forked.messages)


def test_loop_fork_defaults_goal_to_parent(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    parent = loop.start(goal="root goal")
    forked = loop.fork(parent.id)
    assert forked.goal == "root goal"
    assert forked.title == "root goal"


# ---------- SQLite round-trip ----------


def test_sqlite_store_round_trips_new_session_fields(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.sqlite")
    created = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    parent = Session(
        id="ses_parent",
        goal="parent",
        created_at=created,
        title="parent",
    )
    store.create(parent)
    s = Session(
        id="ses_abc",
        goal="round trip",
        status="waiting_user",
        turn_count=3,
        step_count=7,
        created_at=created,
        last_step_at=created,
        parent_session_id="ses_parent",
        title="round trip",
    )
    store.create(s)
    loaded = store.get("ses_abc")
    assert loaded.step_count == 7
    assert loaded.last_step_at == created
    assert loaded.parent_session_id == "ses_parent"
    assert loaded.title == "round trip"
    assert loaded.status == "waiting_user"


def test_sqlite_store_save_updates_lifecycle_fields(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.sqlite")
    s = Session(id="ses_x", goal="g")
    store.create(s)

    s.step_count = 4
    s.status = "done"
    s.title = "updated"
    s.last_step_at = datetime(2026, 5, 23, 13, 0, tzinfo=UTC)
    store.save(s)

    loaded = store.get("ses_x")
    assert loaded.step_count == 4
    assert loaded.status == "done"
    assert loaded.title == "updated"
    assert loaded.last_step_at == datetime(2026, 5, 23, 13, 0, tzinfo=UTC)


# ---------- migration ----------


def test_v1_database_migrates_to_v2_in_place(tmp_path: Path) -> None:
    """A database created at schema v1 should pick up the v2 columns
    on next connect, with existing rows defaulting to step_count=0
    and NULL for the new optional fields."""
    db_path = tmp_path / "legacy.sqlite"

    # Hand-build a v1 schema and insert one session, mimicking an
    # older deployment.
    legacy = sqlite3.connect(str(db_path))
    legacy.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            status TEXT NOT NULL,
            turn_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tool_call_id TEXT,
            ord INTEGER NOT NULL
        );
        CREATE TABLE schema_version (
            version INTEGER NOT NULL PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        INSERT INTO schema_version VALUES (1, '2026-01-01T00:00:00+00:00');
        INSERT INTO sessions VALUES (
            'ses_legacy', 'legacy goal', 'running', 0, '2026-01-01T00:00:00+00:00'
        );
        """
    )
    legacy.commit()
    legacy.close()

    conn = connect(db_path)
    new_version = apply_migrations(conn)
    assert new_version == 5
    assert current_version(conn) == 5
    conn.close()

    store = SqliteSessionStore(db_path)
    loaded = store.get("ses_legacy")
    assert loaded.goal == "legacy goal"
    assert loaded.step_count == 0
    assert loaded.last_step_at is None
    assert loaded.parent_session_id is None
    assert loaded.title is None
    assert loaded.budget_usage.tokens_total == 0


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "twice.sqlite"
    conn = connect(db_path)
    apply_migrations(conn)
    second = apply_migrations(conn)
    assert second == 5
    # No duplicate insert into schema_version.
    rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    assert [r["version"] for r in rows] == [1, 2, 3, 4, 5]


# ---------- ReplayModel + new Decision kind compatibility ----------


def test_decision_kind_ask_user_validates() -> None:
    Decision(kind="ask_user", assistant_message="?")
    Decision(kind="final", assistant_message="!")
