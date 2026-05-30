"""Tests for spawn_sub_agent multi-agent PoC."""

from __future__ import annotations

from pathlib import Path

from span_assertions import read_span_records

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.replay import ReplaySpanRecorder
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.local_span_recorder import LocalSpanRecorder
from harnesslab.telemetry.span_attributes import SPAN_TURN
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.spawn_sub_agent import SpawnSubAgentTool


def _spawn_loop(tmp_path: Path, recorder: LocalSpanRecorder) -> tuple[HarnessLoop, ToolRegistry]:
    tools = ToolRegistry()
    loop_holder: list[HarnessLoop] = []
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(tmp_path, enable_spawn_sub_agent=True),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
        clock=SystemClock(),
        ids=UuidIdProvider(),
        workspace_root=tmp_path,
    )
    loop_holder.append(loop)
    tools.register(SpawnSubAgentTool(lambda: loop_holder[0]))
    return loop, tools


def test_spawn_sub_agent_creates_child(tmp_path: Path) -> None:
    spans_path = tmp_path / "spans.jsonl"
    recorder = LocalSpanRecorder(spans_path)
    loop, _ = _spawn_loop(tmp_path, recorder)
    parent = loop.start(goal="supervisor")
    loop.run_session(
        parent.id,
        '/tool spawn_sub_agent {"goal": "child task", "max_steps": 1}',
        max_steps=2,
    )
    child = loop._sessions.list(parent_session_id=parent.id)[0]  # noqa: SLF001
    child_turns = [
        s
        for s in read_span_records(spans_path)
        if s.session_id == child.id and s.name == SPAN_TURN
    ]
    assert child_turns


def test_spawn_sub_agent_emits_sub_agent_run_span(tmp_path: Path) -> None:
    spans_path = tmp_path / "spans.jsonl"
    recorder = LocalSpanRecorder(spans_path)
    loop, _ = _spawn_loop(tmp_path, recorder)
    parent = loop.start(goal="supervisor")
    loop.run_session(
        parent.id,
        '/tool spawn_sub_agent {"goal": "child task", "max_steps": 1}',
        max_steps=2,
    )
    sub_runs = [
        s
        for s in read_span_records(spans_path)
        if s.name == "sub_agent.run" and s.session_id == parent.id
    ]
    assert len(sub_runs) == 1
    assert sub_runs[0].attributes.get("harnesslab.sub_agent.goal")
    assert sub_runs[0].links


def test_spawn_sub_agent_links_child_turn(tmp_path: Path) -> None:
    spans_path = tmp_path / "spans.jsonl"
    recorder = LocalSpanRecorder(spans_path)
    loop, _ = _spawn_loop(tmp_path, recorder)
    parent = loop.start(goal="supervisor")
    loop.run_session(
        parent.id,
        '/tool spawn_sub_agent {"goal": "child task", "max_steps": 1}',
        max_steps=2,
    )
    sub_runs = [
        s
        for s in read_span_records(spans_path)
        if s.name == "sub_agent.run" and s.session_id == parent.id
    ]
    assert sub_runs[0].metrics.get("duration_ms") is not None
    assert sub_runs[0].attributes.get("harnesslab.child_session.id")


def test_spawn_sub_agent_child_budget_isolated_from_parent(tmp_path: Path) -> None:
    tools = ToolRegistry()
    loop_holder: list[HarnessLoop] = []
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(tmp_path, enable_spawn_sub_agent=True),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=ReplaySpanRecorder(),
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
    spans_path = tmp_path / "spans.jsonl"
    recorder = LocalSpanRecorder(spans_path)
    tools = ToolRegistry()
    loop_holder: list[HarnessLoop] = []
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(tmp_path, enable_spawn_sub_agent=True),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
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
    child = loop._sessions.list(parent_session_id=parent.id)[0]  # noqa: SLF001
    loop.run_session(
        child.id,
        '/tool spawn_sub_agent {"goal": "grandchild", "max_steps": 1}',
        max_steps=2,
    )
    tool_msgs = [
        m.content
        for m in loop._sessions.get(child.id).messages  # noqa: SLF001
        if m.role == "tool"
    ]
    assert any("max sub-agent depth" in msg for msg in tool_msgs)
