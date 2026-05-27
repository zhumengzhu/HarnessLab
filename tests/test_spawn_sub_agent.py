"""Tests for spawn_sub_agent multi-agent PoC."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.replay.trace_reader import read_trace
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.spawn_sub_agent import SpawnSubAgentTool


def test_spawn_sub_agent_creates_child(tmp_path: Path) -> None:
    tools = ToolRegistry()
    loop_holder: list[HarnessLoop] = []
    trace_path = tmp_path / "trace.jsonl"
    recorder = JsonlTraceRecorder(trace_path)
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(tmp_path, enable_spawn_sub_agent=True),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
        clock=SystemClock(),
        ids=UuidIdProvider(),
        workspace_root=tmp_path,
    )
    loop_holder.append(loop)
    tools.register(SpawnSubAgentTool(lambda: loop_holder[0]))
    parent = loop.start(goal="supervisor")
    loop.run_session(
        parent.id,
        '/tool spawn_sub_agent {"goal": "child task", "max_steps": 1}',
        max_steps=2,
    )
    child_events = [
        e
        for e in read_trace(trace_path)
        if e.event_type == "session_started" and e.payload.get("parent_session_id")
    ]
    assert child_events


def test_spawn_sub_agent_depth_limit(tmp_path: Path) -> None:
    tools = ToolRegistry()
    loop_holder: list[HarnessLoop] = []
    trace_path = tmp_path / "trace.jsonl"
    recorder = JsonlTraceRecorder(trace_path)
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(tmp_path, enable_spawn_sub_agent=True),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
        clock=SystemClock(),
        ids=UuidIdProvider(),
        workspace_root=tmp_path,
    )
    loop_holder.append(loop)
    tools.register(SpawnSubAgentTool(lambda: loop_holder[0], max_depth=1))
    parent = loop.start(goal="supervisor")
    loop.run_session(
        parent.id,
        '/tool spawn_sub_agent {"goal": "child", "max_steps": 1}',
        max_steps=2,
    )
    child_events = [
        e
        for e in read_trace(trace_path)
        if e.event_type == "session_started" and e.payload.get("parent_session_id")
    ]
    assert child_events
    child_id = child_events[0].run_id
    loop.run_session(
        child_id,
        '/tool spawn_sub_agent {"goal": "grandchild", "max_steps": 1}',
        max_steps=2,
    )
    tool_msgs = [
        m.content
        for m in loop._sessions.get(child_id).messages  # noqa: SLF001
        if m.role == "tool"
    ]
    assert any("max sub-agent depth" in msg for msg in tool_msgs)
