"""Tests for spawn_sub_agent multi-agent PoC."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.replay import ReplayTraceRecorder
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


def test_spawn_sub_agent_emits_parent_trace_event(tmp_path: Path) -> None:
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
    spawned = [
        e
        for e in read_trace(trace_path)
        if e.event_type == "sub_agent_spawned" and e.session_id == parent.id
    ]
    assert len(spawned) == 1
    assert spawned[0].payload["parent_session_id"] == parent.id
    assert spawned[0].payload["goal"] == "child task"


def test_spawn_sub_agent_emits_completed_event(tmp_path: Path) -> None:
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
    completed = [
        e
        for e in read_trace(trace_path)
        if e.event_type == "sub_agent_completed" and e.session_id == parent.id
    ]
    assert len(completed) == 1
    assert completed[0].payload["parent_session_id"] == parent.id
    assert completed[0].payload["goal"] == "child task"


def test_spawn_sub_agent_child_budget_isolated_from_parent(tmp_path: Path) -> None:
    tools = ToolRegistry()
    loop_holder: list[HarnessLoop] = []
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(tmp_path, enable_spawn_sub_agent=True),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=ReplayTraceRecorder(),
        clock=SystemClock(),
        ids=UuidIdProvider(),
        workspace_root=tmp_path,
    )
    loop_holder.append(loop)
    tools.register(SpawnSubAgentTool(lambda: loop_holder[0]))
    parent = loop.start(goal="supervisor")
    loop.run_session(
        parent.id,
        '/tool spawn_sub_agent {"goal": "child task", "max_steps": 2}',
        max_steps=2,
    )
    parent_after = loop._sessions.get(parent.id)  # noqa: SLF001
    child = next(
        s
        for s in loop._sessions.list(parent_session_id=parent.id)  # noqa: SLF001
    )
    assert child.parent_session_id == parent.id
    assert child.budget_usage is not parent_after.budget_usage
    assert child.budget_usage.llm_calls_total >= 1
    assert parent_after.budget_usage.llm_calls_total >= 1
    assert (
        parent_after.budget_usage.llm_calls_total + child.budget_usage.llm_calls_total
        > max(parent_after.budget_usage.llm_calls_total, child.budget_usage.llm_calls_total)
    )


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
