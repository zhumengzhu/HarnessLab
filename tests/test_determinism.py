"""Contract test: with injected Clock/Id, two runs produce byte-identical traces."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.simple_model import SimpleModel
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry


class FrozenClock:
    """Clock that ticks by a fixed delta on every read. Replay-friendly."""

    def __init__(self, start: datetime, step: timedelta = timedelta(milliseconds=1)) -> None:
        self._t = start
        self._step = step

    def now(self) -> datetime:
        current = self._t
        self._t = self._t + self._step
        return current


class SeqIdProvider:
    """Monotonic sequential IDs scoped per prefix. Replay-friendly."""

    def __init__(self) -> None:
        self._counters: dict[str, count[int]] = {}

    def new_id(self, prefix: str) -> str:
        if prefix not in self._counters:
            self._counters[prefix] = count(1)
        return f"{prefix}_{next(self._counters[prefix]):06d}"


def _build_loop(workspace: Path, trace_path: Path) -> HarnessLoop:
    sessions = InMemorySessionStore()
    policy = DefaultPolicy(workspace_root=workspace)
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace))
    tools.register(WriteFileTool(workspace))
    trace = JsonlTraceRecorder(trace_path)
    return HarnessLoop(
        model=SimpleModel(),
        policy=policy,
        sessions=sessions,
        tools=tools,
        trace=trace,
        clock=FrozenClock(start=datetime(2026, 1, 1, tzinfo=UTC)),
        ids=SeqIdProvider(),
    )


def _run_scenario(workspace: Path, trace_path: Path) -> None:
    """Drive only events whose payload is independent of the workspace path."""

    loop = _build_loop(workspace, trace_path)
    session = loop.start(goal="deterministic")
    loop.run_turn(session.id, "hello")
    loop.run_turn(session.id, '/tool read_file {"path":"../escape.txt"}')


def test_two_runs_produce_identical_traces(tmp_path: Path) -> None:
    ws_a = tmp_path / "a"
    ws_b = tmp_path / "b"
    ws_a.mkdir()
    ws_b.mkdir()
    trace_a = tmp_path / "trace_a.jsonl"
    trace_b = tmp_path / "trace_b.jsonl"

    _run_scenario(ws_a, trace_a)
    _run_scenario(ws_b, trace_b)

    lines_a = [json.loads(line) for line in trace_a.read_text().splitlines() if line]
    lines_b = [json.loads(line) for line in trace_b.read_text().splitlines() if line]

    assert lines_a == lines_b
    assert any(ev["event_type"] == "session_started" for ev in lines_a)
    assert any(ev["event_type"] == "decision_made" for ev in lines_a)
    assert any(ev["event_type"] == "tool_denied" for ev in lines_a)


def test_message_session_id_is_populated(tmp_path: Path) -> None:
    loop = _build_loop(tmp_path, tmp_path / "trace.jsonl")
    session = loop.start(goal="session id")
    loop.run_turn(session.id, "hello")

    assert len(session.messages) >= 2
    for msg in session.messages:
        assert msg.session_id == session.id
