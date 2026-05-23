"""Tests for session-scoped memory read/write in the loop."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.memory_policy import session_memory_key
from harnesslab.core.models import Decision
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.registry import ToolRegistry


def test_remember_writes_and_next_turn_reads(tmp_path: Path) -> None:
    memory = InMemoryMemoryStore()
    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel(
            decisions=[
                Decision(kind="final", assistant_message="second reply"),
            ]
        ),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=ToolRegistry(),
        trace=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        memory=memory,
    )
    session = loop.start(goal="memory test")
    assert loop.run_session(session.id, "/remember api prefers json") == (
        "Stored in session memory."
    )
    key = session_memory_key(session.id)
    notes = memory.get(key)
    assert notes is not None
    assert "api prefers json" in notes

    loop.run_session(session.id, "hello two")
    types = [e.event_type for e in recorder.events]
    assert "memory_read" in types
    assert types.count("memory_written") == 1


def test_final_turn_does_not_auto_write_memory(tmp_path: Path) -> None:
    memory = InMemoryMemoryStore()
    loop = HarnessLoop(
        model=ReplayModel([Decision(kind="final", assistant_message="ok")]),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=ToolRegistry(),
        trace=ReplayTraceRecorder(),
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        memory=memory,
    )
    session = loop.start(goal="g")
    loop.run_session(session.id, "plain question")
    assert memory.get(session_memory_key(session.id)) is None


def test_loop_without_memory_store_skips_events(tmp_path: Path) -> None:
    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel([Decision(kind="final", assistant_message="ok")]),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=ToolRegistry(),
        trace=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        memory=None,
    )
    session = loop.start(goal="g")
    reply = loop.run_session(session.id, "/remember note")
    assert reply == "Memory store is not configured."
    types = {e.event_type for e in recorder.events}
    assert "memory_written" not in types
    assert "memory_read" not in types
