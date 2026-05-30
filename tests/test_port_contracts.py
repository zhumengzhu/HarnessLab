"""Minimal compliance tests for every stable Port.

One test per Port, exercising the default implementation against the
contract: argument shape, return shape, and key behavioral invariants.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from harnesslab.artifact.in_memory import InMemoryArtifactStore
from harnesslab.core.contracts import (
    ArtifactStorePort,
    ClockPort,
    IdPort,
    MemoryStorePort,
    ModelPort,
    PolicyPort,
    SessionStorePort,
    SpanRecorderPort,
    ToolPort,
)
from harnesslab.core.models import (
    Decision,
    Session,
    ToolCall,
    ToolResult,
)
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.memory.sqlite_store import SqliteMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.session.sqlite_store import SqliteSessionStore
from harnesslab.telemetry.memory_span_recorder import MemorySpanRecorder
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.shell_tool import RunShellSafeTool


def test_model_port_contract() -> None:
    model: ModelPort = SimpleModel()
    session = Session(goal="contract")
    decision = model.decide(session, "hello")
    assert isinstance(decision, Decision)
    assert decision.kind in {"assistant", "plan", "tool", "final", "ask_user"}


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


@pytest.fixture(params=["in_memory", "sqlite"])
def session_store(request: pytest.FixtureRequest, tmp_path: Path) -> SessionStorePort:
    backend = request.param
    if backend == "in_memory":
        return InMemorySessionStore()
    if backend == "sqlite":
        return SqliteSessionStore(tmp_path / "sessions.sqlite")
    raise ValueError(f"unknown session store backend: {backend}")


@pytest.fixture(params=["in_memory", "sqlite"])
def memory_store(request: pytest.FixtureRequest, tmp_path: Path) -> MemoryStorePort:
    backend = request.param
    if backend == "in_memory":
        return InMemoryMemoryStore()
    if backend == "sqlite":
        return SqliteMemoryStore(tmp_path / "memory.sqlite")
    raise ValueError(f"unknown memory store backend: {backend}")


def test_session_store_port_contract(session_store: SessionStorePort) -> None:
    session = Session(goal="round-trip")
    session_store.create(session)

    fetched = session_store.get(session.id)
    # Structural equality, not `is`, so SQLite-backed stores (which return
    # freshly hydrated objects) satisfy the same contract.
    assert fetched.id == session.id
    assert fetched.goal == session.goal
    assert fetched.turn_count == session.turn_count

    session.turn_count = 3
    session_store.save(session)
    assert session_store.get(session.id).turn_count == 3


def test_memory_store_port_contract(memory_store: MemoryStorePort) -> None:
    assert memory_store.get("missing") is None
    memory_store.put("k", "v")
    assert memory_store.get("k") == "v"
    memory_store.put("k", "v2")
    assert memory_store.get("k") == "v2"


def test_span_recorder_port_contract() -> None:
    recorder: SpanRecorderPort = MemorySpanRecorder()
    handle = recorder.start_span(
        "harnesslab.turn",
        session_id="ses_test",
        trace_id="a" * 32,
        turn_index=0,
    )
    record = recorder.end_span(handle)
    assert record.name == "harnesslab.turn"
    assert record.session_id == "ses_test"


def test_artifact_store_port_contract() -> None:
    store: ArtifactStorePort = InMemoryArtifactStore()
    ref = store.put(b"hello", mime="text/plain", session_id="ses_a", artifact_id="art_a")
    assert ref == "art_a"
    assert store.get(ref) == b"hello"
    meta = store.metadata(ref)
    assert meta.id == "art_a"
    assert meta.session_id == "ses_a"


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
