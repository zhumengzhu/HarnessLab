"""Tests for Phase 4.5 workspace-scoped memory."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.memory_policy import workspace_memory_key
from harnesslab.core.models import Decision
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.registry import ToolRegistry


def test_remember_global_persists_across_sessions(tmp_path: Path) -> None:
    memory = InMemoryMemoryStore()
    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel(
            decisions=[
                Decision(kind="final", assistant_message="saw workspace notes"),
            ]
        ),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=ToolRegistry(),
        trace=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        memory=memory,
        workspace_root=tmp_path,
    )
    session_a = loop.start(goal="first")
    assert loop.run_session(session_a.id, "/remember-global deploy Fridays") == (
        "Stored in workspace memory."
    )
    key = workspace_memory_key(tmp_path)
    notes = memory.get(key)
    assert notes is not None
    assert "deploy Fridays" in notes

    session_b = loop.start(goal="second")
    loop.run_session(session_b.id, "hello")
    types = [e.event_type for e in recorder.events]
    assert "workspace_memory_written" in types
    assert "workspace_memory_read" in types
