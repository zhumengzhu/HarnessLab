"""Tests for ``harnesslab session ls/show/resume/fork``."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from harnesslab import cli
from harnesslab.core.models import Message, Session
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.session.sqlite_store import SqliteSessionStore

# ---------- SessionStorePort.list ----------


def _seed(store) -> tuple[Session, Session]:
    older = Session(
        id="ses_old",
        goal="older",
        status="done",
        step_count=2,
        turn_count=1,
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        title="older",
    )
    newer = Session(
        id="ses_new",
        goal="newer",
        status="waiting_user",
        step_count=5,
        turn_count=2,
        created_at=datetime(2026, 5, 23, 10, 0, tzinfo=UTC),
        title="newer",
    )
    store.create(older)
    store.create(newer)
    older.budget_usage.tokens_total = 100
    older.budget_usage.last_budget_status = "ok"
    newer.budget_usage.tokens_total = 300
    newer.budget_usage.last_budget_status = "soft_exceeded"
    store.save(older)
    store.save(newer)
    return older, newer


def test_in_memory_store_list_newest_first() -> None:
    store = InMemorySessionStore()
    older, newer = _seed(store)
    assert [s.id for s in store.list()] == [newer.id, older.id]


def test_in_memory_store_list_filters_by_status() -> None:
    store = InMemorySessionStore()
    _seed(store)
    waiting = store.list(status="waiting_user")
    assert [s.id for s in waiting] == ["ses_new"]


def test_in_memory_store_list_respects_limit() -> None:
    store = InMemorySessionStore()
    _seed(store)
    assert len(store.list(limit=1)) == 1


def test_in_memory_store_list_filters_by_parent() -> None:
    store = InMemorySessionStore()
    parent = Session(
        id="ses_parent",
        goal="parent",
        created_at=datetime(2026, 5, 23, 10, 0, tzinfo=UTC),
    )
    child = Session(
        id="ses_child",
        goal="child",
        parent_session_id="ses_parent",
        created_at=datetime(2026, 5, 23, 11, 0, tzinfo=UTC),
    )
    other = Session(
        id="ses_other",
        goal="other",
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
    )
    store.create(parent)
    store.create(child)
    store.create(other)
    rows = store.list(parent_session_id="ses_parent")
    assert [s.id for s in rows] == ["ses_child"]


def test_sqlite_store_list_newest_first(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.sqlite")
    older, newer = _seed(store)
    rows = store.list()
    assert [s.id for s in rows] == [newer.id, older.id]
    # `list` doesn't eagerly load messages.
    assert rows[0].messages == []


def test_sqlite_store_list_filters_and_limits(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.sqlite")
    _seed(store)
    waiting = store.list(status="waiting_user", limit=10)
    assert [s.id for s in waiting] == ["ses_new"]


# ---------- CLI: session ls / show / resume / fork ----------


def _seed_sqlite_with_one_session(tmp_path: Path) -> str:
    (tmp_path / ".harnesslab").mkdir(parents=True, exist_ok=True)
    store = SqliteSessionStore(tmp_path / ".harnesslab" / "state.sqlite")
    sess = Session(
        id="ses_cli",
        goal="cli probe",
        status="done",
        turn_count=1,
        step_count=2,
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        title="cli probe",
    )
    sess.messages.append(
        Message(
            id="msg_u",
            role="user",
            content="hello there",
            session_id=sess.id,
            created_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        )
    )
    sess.messages.append(
        Message(
            id="msg_a",
            role="assistant",
            content="hi back",
            session_id=sess.id,
            created_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        )
    )
    sess.budget_usage.llm_calls_total = 3
    sess.budget_usage.tool_calls_total = 1
    sess.budget_usage.tokens_total = 210
    sess.budget_usage.wall_time_ms_total = 1550
    sess.budget_usage.cost_usd_total = 0.0042
    sess.budget_usage.last_budget_status = "soft_exceeded"
    store.create(sess)
    store.close()
    return sess.id


def test_session_ls_prints_table_with_seeded_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sess_id = _seed_sqlite_with_one_session(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "ls",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "ID" in out
    assert "TOKENS" in out
    assert "BUDGET" in out
    assert "PARENT" in out
    assert sess_id in out
    assert "done" in out
    assert "cli probe" in out


def test_session_ls_empty_store_prints_placeholder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["harnesslab", "session", "--workspace-root", str(tmp_path), "ls"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    assert "(no sessions)" in capsys.readouterr().out


def test_session_show_prints_metadata_and_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sess_id = _seed_sqlite_with_one_session(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "show",
            sess_id,
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Session:" in out
    assert sess_id in out
    assert "Status:    done" in out
    assert "Steps:     2" in out
    assert "Budget:" in out
    assert "status:   soft_exceeded" in out
    assert "tokens:   210" in out
    assert "user: hello there" in out
    assert "assistant: hi back" in out


def test_session_show_include_children_lists_child_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".harnesslab").mkdir(parents=True, exist_ok=True)
    store = SqliteSessionStore(tmp_path / ".harnesslab" / "state.sqlite")
    parent = Session(
        id="ses_parent",
        goal="supervisor",
        status="done",
        turn_count=1,
        step_count=2,
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        title="supervisor",
    )
    child = Session(
        id="ses_child",
        goal="research child",
        status="done",
        turn_count=1,
        step_count=3,
        parent_session_id=parent.id,
        created_at=datetime(2026, 5, 23, 12, 5, tzinfo=UTC),
        title="research child",
    )
    child.budget_usage.tokens_total = 420
    child.budget_usage.cost_usd_total = 0.001
    store.create(parent)
    store.create(child)
    store.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "show",
            parent.id,
            "--include-children",
            "--no-messages",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Children (1):" in out
    assert child.id in out
    assert "research child" in out
    assert "tokens=420" in out


def test_session_show_no_messages_flag_omits_transcript(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sess_id = _seed_sqlite_with_one_session(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "show",
            sess_id,
            "--no-messages",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Session:" in out
    assert "user: hello there" not in out


def test_session_show_unknown_id_returns_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_sqlite_with_one_session(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "show",
            "ses_does_not_exist",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_USAGE
    assert "session not found" in capsys.readouterr().err


def test_session_resume_runs_another_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sess_id = _seed_sqlite_with_one_session(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "resume",
            sess_id,
            "/final all wrapped up",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "all wrapped up" in out

    store = SqliteSessionStore(tmp_path / ".harnesslab" / "state.sqlite")
    refreshed = store.get(sess_id)
    store.close()
    # The original seed put turn_count=1; the resume adds another turn.
    assert refreshed.turn_count == 2
    assert refreshed.step_count == 3
    assert refreshed.status == "done"


def test_session_resume_unknown_id_returns_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_sqlite_with_one_session(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "resume",
            "ses_missing",
            "anything",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_USAGE


def test_session_fork_creates_branch_with_parent_pointer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent_id = _seed_sqlite_with_one_session(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "fork",
            parent_id,
            "--goal",
            "try a different angle",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    new_id = capsys.readouterr().out.strip()
    assert new_id.startswith("ses_")
    assert new_id != parent_id

    store = SqliteSessionStore(tmp_path / ".harnesslab" / "state.sqlite")
    forked = store.get(new_id)
    store.close()
    assert forked.parent_session_id == parent_id
    assert forked.goal == "try a different angle"
    assert forked.title == "try a different angle"
    # Forked session inherits the parent's messages by value.
    assert [m.content for m in forked.messages] == ["hello there", "hi back"]


def test_session_fork_unknown_id_returns_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_sqlite_with_one_session(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "session",
            "--workspace-root",
            str(tmp_path),
            "fork",
            "ses_missing",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_USAGE
