"""Tests for checkpoint / rewind (Phase 5.9)."""

from __future__ import annotations

from pathlib import Path

from harnesslab.checkpoint.store import SqliteCheckpointStore, restore_snapshots
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.replay.trace_reader import read_trace
from harnesslab.session.sqlite_store import SqliteSessionStore
from harnesslab.storage.sqlite import apply_migrations, connect
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder
from harnesslab.tools.file_tools import WriteFileTool
from harnesslab.tools.registry import ToolRegistry


def _seed_session(db_path: Path, session_id: str) -> None:
    conn = connect(db_path)
    apply_migrations(conn)
    conn.execute(
        """
        INSERT INTO sessions (id, goal, status, turn_count, created_at, step_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, "g", "running", 0, "2026-01-01T00:00:00+00:00", 0),
    )
    conn.commit()
    conn.close()


def test_rewind_restores_file_content(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    session_id = "ses_cp_test"
    _seed_session(db_path, session_id)
    store = SqliteCheckpointStore(db_path)
    target = tmp_path / "note.txt"
    target.write_text("original", encoding="utf-8")
    snapshots = {"note.txt": "original"}
    cp_id = "cp_test1"
    store.create(
        checkpoint_id=cp_id,
        session_id=session_id,
        tool_name="write_file",
        tool_args={"path": "note.txt", "content": "changed"},
        snapshots=snapshots,
    )
    target.write_text("changed", encoding="utf-8")
    checkpoint = store.get(cp_id)
    touched = restore_snapshots(tmp_path, checkpoint.snapshots)
    assert "note.txt" in touched
    assert target.read_text(encoding="utf-8") == "original"
    store.close()


def test_loop_emits_checkpoint_created(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    store = SqliteCheckpointStore(db_path)
    tools = ToolRegistry()
    tools.register(WriteFileTool(tmp_path))
    trace_path = tmp_path / "trace.jsonl"
    recorder = JsonlTraceRecorder(trace_path)
    sessions = SqliteSessionStore(db_path)
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(tmp_path),
        sessions=sessions,
        tools=tools,
        trace=recorder,
        clock=SystemClock(),
        ids=UuidIdProvider(),
        checkpoint_store=store,
        workspace_root=tmp_path,
    )
    session = loop.start(goal="checkpoint test")
    loop.run_session(
        session.id,
        '/tool write_file {"path": "a.txt", "content": "hello"}',
        max_steps=2,
    )
    events = [e.event_type for e in read_trace(trace_path)]
    assert "checkpoint_created" in events
    store.close()
    sessions.close()
