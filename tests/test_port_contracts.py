"""Minimal compliance tests for every stable Port.

One test per Port, exercising the default implementation against the
contract: argument shape, return shape, and key behavioral invariants.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from harnesslab.core.contracts import (
    ClockPort,
    IdPort,
    ModelPort,
    PolicyPort,
    SessionStorePort,
    ToolPort,
    TraceRecorderPort,
)
from harnesslab.core.models import (
    Decision,
    Session,
    ToolCall,
    ToolResult,
    TraceEvent,
)
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.shell_tool import RunShellSafeTool


def test_model_port_contract() -> None:
    model: ModelPort = SimpleModel()
    session = Session(goal="contract")
    decision = model.decide(session, "hello")
    assert isinstance(decision, Decision)
    assert decision.kind in {"assistant", "tool"}


def test_policy_port_contract(tmp_path: Path) -> None:
    policy: PolicyPort = DefaultPolicy(workspace_root=tmp_path)
    call = ToolCall(name="read_file", args={"path": "a.txt"})
    allowed, reason = policy.allow_tool(call)
    assert isinstance(allowed, bool)
    assert isinstance(reason, str)
    assert reason


def test_tool_port_contract_file_tools(tmp_path: Path) -> None:
    for tool in (ReadFileTool(tmp_path), WriteFileTool(tmp_path)):
        adapted: ToolPort = tool
        assert isinstance(adapted.name, str) and adapted.name
        assert isinstance(adapted.description, str) and adapted.description
        assert isinstance(adapted.args_schema, dict) and "type" in adapted.args_schema


def test_tool_port_contract_shell_tool(tmp_path: Path) -> None:
    adapted: ToolPort = RunShellSafeTool(tmp_path)
    assert adapted.name == "run_shell_safe"
    assert isinstance(adapted.args_schema, dict)
    result = adapted.execute(ToolCall(name="run_shell_safe", args={"command": "pwd"}))
    assert isinstance(result, ToolResult)
    assert isinstance(result.ok, bool)


def test_session_store_port_contract() -> None:
    store: SessionStorePort = InMemorySessionStore()
    session = Session(goal="round-trip")
    store.create(session)
    fetched = store.get(session.id)
    assert fetched is session
    session.turn_count = 3
    store.save(session)
    assert store.get(session.id).turn_count == 3


def test_memory_store_port_contract() -> None:
    store = InMemoryMemoryStore()
    assert store.get("missing") is None
    store.put("k", "v")
    assert store.get("k") == "v"


def test_trace_recorder_port_contract(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    recorder: TraceRecorderPort = JsonlTraceRecorder(trace_path)
    event = TraceEvent(
        run_id="ses_test",
        session_id="ses_test",
        event_type="contract_probe",
        payload={"k": 1},
    )
    recorder.record(event)
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "contract_probe" in lines[0]


def test_clock_port_contract() -> None:
    clock: ClockPort = SystemClock()
    now1 = clock.now()
    now2 = clock.now()
    assert isinstance(now1, datetime)
    assert now1.tzinfo is not None, "ClockPort.now must return a tz-aware datetime"
    assert now2 >= now1


def test_id_port_contract() -> None:
    ids: IdPort = UuidIdProvider()
    a = ids.new_id("ses")
    b = ids.new_id("ses")
    assert a.startswith("ses_")
    assert b.startswith("ses_")
    assert a != b
