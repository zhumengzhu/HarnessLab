"""Tests for the Step 5 replay subsystem."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import pytest

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import TraceEvent
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.eval.loader import load_suite
from harnesslab.eval.runner import _build_tool_registry, _limits_for_task
from harnesslab.eval.task import Task
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.replay import (
    UnreplayableTraceError,
    detect_divergence,
    group_by_session,
    read_trace,
    replay_session,
)
from harnesslab.session.in_memory import InMemorySessionStore

TASKS_DIR = Path(__file__).resolve().parents[1] / "eval" / "tasks"


def _capture_task_trace(task: Task) -> list[TraceEvent]:
    """Drive a task end-to-end against the production loop with deterministic
    clock/ids, and return the recorded trace events. This is the same
    machinery the eval runner uses, expressed locally so the replay tests
    don't depend on the runner's private surface."""

    workspace = Path(tempfile.mkdtemp(prefix="hl-replay-trace-"))
    limits = _limits_for_task(task)
    tools = _build_tool_registry(workspace, limits)
    recorder = ReplayTraceRecorder()
    model = ReplayModel(decisions=task.decisions) if task.decisions else SimpleModel()
    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(workspace_root=workspace),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        limits=limits,
        memory=InMemoryMemoryStore(),
    )
    session = loop.start(goal=task.goal)
    for turn in task.turns:
        loop.run_session(session.id, turn.input, max_steps=turn.max_steps)
    return recorder.events


# ---------- trace_reader ----------


def test_read_trace_parses_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    payload = {
        "run_id": "r1",
        "session_id": "ses_000001",
        "event_type": "session_started",
        "payload": {"goal": "x"},
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    path.write_text(json.dumps(payload) + "\n\n", encoding="utf-8")
    events = read_trace(path)
    assert len(events) == 1
    assert events[0].event_type == "session_started"


def test_read_trace_rejects_malformed_line(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_trace(path)


def test_group_by_session_preserves_order(tmp_path: Path) -> None:
    def evt(sid: str, t: str) -> TraceEvent:
        return TraceEvent(run_id=sid, session_id=sid, event_type=t)

    events = [evt("s1", "a"), evt("s2", "a"), evt("s1", "b")]
    grouped = group_by_session(events)
    assert list(grouped.keys()) == ["s1", "s2"]
    assert [e.event_type for e in grouped["s1"]] == ["a", "b"]


# ---------- replayer happy path against real eval traces ----------


def test_replay_matches_eval_task_traces() -> None:
    """Every shipped eval task's trace must replay to a divergence-free
    report. This is the headline guarantee of Step 5."""
    suite = load_suite(TASKS_DIR)
    for task in suite.tasks:
        original = _capture_task_trace(task)
        replayed = replay_session(original)
        report = detect_divergence(original, replayed)
        assert report.matched, (
            f"{task.name} diverged after replay:\n{report.render()}"
        )


def test_replay_round_trips_multi_step_turn() -> None:
    """A single user turn that spans multiple model decisions (tool
    then final, Phase 2.1) must round-trip cleanly: the replayer
    collects every decision_made between consecutive
    user_input_received events and re-drives the loop with
    ``max_steps=len(decisions)`` so step ordering and outcomes
    remain stable."""
    suite = load_suite(TASKS_DIR)
    task = next(t for t in suite.tasks if t.name == "multi_step_tool_then_final")
    original = _capture_task_trace(task)

    # Sanity: the captured trace genuinely contains 2 decisions in 1 turn.
    decisions_per_turn = sum(1 for e in original if e.event_type == "decision_made")
    user_inputs = sum(1 for e in original if e.event_type == "user_input_received")
    assert user_inputs == 1
    assert decisions_per_turn == 2

    replayed = replay_session(original)
    report = detect_divergence(original, replayed)
    assert report.matched, report.render()


def test_replay_returns_session_started_only_when_no_turns() -> None:
    events = [
        TraceEvent(
            run_id="ses_x",
            session_id="ses_x",
            event_type="session_started",
            payload={"goal": "noop"},
        )
    ]
    replayed = replay_session(events)
    assert len(replayed) == 1
    assert replayed[0].event_type == "session_started"
    assert replayed[0].payload == {"goal": "noop"}


# ---------- replayer error cases ----------


def test_replay_empty_trace_raises() -> None:
    with pytest.raises(UnreplayableTraceError):
        replay_session([])


def test_replay_first_event_must_be_session_started() -> None:
    events = [TraceEvent(run_id="x", session_id="x", event_type="decision_made")]
    with pytest.raises(UnreplayableTraceError):
        replay_session(events)


def test_replay_user_input_without_decision_raises() -> None:
    events = [
        TraceEvent(
            run_id="x",
            session_id="x",
            event_type="session_started",
            payload={"goal": "g"},
        ),
        TraceEvent(
            run_id="x",
            session_id="x",
            event_type="user_input_received",
            payload={"turn_index": 0, "user_input": "hi"},
        ),
        TraceEvent(
            run_id="x",
            session_id="x",
            event_type="tool_executed",
            payload={"tool": "read_file"},
        ),
    ]
    with pytest.raises(UnreplayableTraceError):
        replay_session(events)


def test_replay_user_input_missing_payload_raises() -> None:
    events = [
        TraceEvent(
            run_id="x",
            session_id="x",
            event_type="session_started",
            payload={"goal": "g"},
        ),
        TraceEvent(
            run_id="x",
            session_id="x",
            event_type="user_input_received",
            payload={"turn_index": 0},  # missing user_input
        ),
        TraceEvent(
            run_id="x",
            session_id="x",
            event_type="decision_made",
            payload={"kind": "assistant"},
        ),
    ]
    with pytest.raises(UnreplayableTraceError):
        replay_session(events)


# ---------- divergence: tampering must be detected ----------


def _eval_trace_for(task_name: str) -> list[TraceEvent]:
    suite = load_suite(TASKS_DIR)
    task = next(t for t in suite.tasks if t.name == task_name)
    return _capture_task_trace(task)


def test_divergence_detects_tampered_decision() -> None:
    original = _eval_trace_for("write_then_read")
    tampered = copy.deepcopy(original)
    # Mutate the first decision_made to a non-matching tool name.
    for ev in tampered:
        if ev.event_type == "decision_made" and ev.payload.get("tool_name") == "write_file":
            ev.payload["tool_name"] = "read_file"
            break
    replayed = replay_session(tampered)
    report = detect_divergence(original, replayed)
    assert not report.matched
    assert any(d.kind in ("event_type", "payload") for d in report.divergences)


def test_divergence_detects_extra_event() -> None:
    original = _eval_trace_for("assistant_fallback")
    replayed = list(original) + [
        TraceEvent(
            run_id=original[0].run_id,
            session_id=original[0].session_id,
            event_type="extra_event",
        )
    ]
    report = detect_divergence(original, replayed)
    assert not report.matched
    assert any(d.kind == "length_mismatch" for d in report.divergences)


def test_divergence_detects_event_type_swap() -> None:
    original = _eval_trace_for("assistant_fallback")
    replayed = copy.deepcopy(original)
    replayed[-1] = TraceEvent(
        run_id=replayed[-1].run_id,
        session_id=replayed[-1].session_id,
        event_type="not_decision_made",
        payload=replayed[-1].payload,
    )
    report = detect_divergence(original, replayed)
    assert not report.matched
    assert any(d.kind == "event_type" for d in report.divergences)


# ---------- divergence normalization: same logical events match ----------


def test_divergence_ignores_id_renaming() -> None:
    base = TraceEvent(
        run_id="ses_aaa",
        session_id="ses_aaa",
        event_type="tool_executed",
        payload={"tool_call_id": "tool_aaa", "tool": "read_file"},
    )
    renamed = TraceEvent(
        run_id="ses_xyz",
        session_id="ses_xyz",
        event_type="tool_executed",
        payload={"tool_call_id": "tool_xyz", "tool": "read_file"},
    )
    # Both traces have one ses_* and one tool_*; normalization should
    # collapse them to ses_001/tool_001 in both, so they match.
    report = detect_divergence([base], [renamed])
    assert report.matched, report.render()


def test_divergence_ignores_timestamps_by_default() -> None:
    a = TraceEvent(
        run_id="r", session_id="r", event_type="x",
        created_at="2026-01-01T00:00:00+00:00",  # type: ignore[arg-type]
    )
    b = TraceEvent(
        run_id="r", session_id="r", event_type="x",
        created_at="2030-12-31T23:59:59+00:00",  # type: ignore[arg-type]
    )
    assert detect_divergence([a], [b]).matched


def test_divergence_strict_mode_flags_timestamp_diff() -> None:
    a = TraceEvent(
        run_id="r", session_id="r", event_type="x",
        created_at="2026-01-01T00:00:00+00:00",  # type: ignore[arg-type]
    )
    b = TraceEvent(
        run_id="r", session_id="r", event_type="x",
        created_at="2030-12-31T23:59:59+00:00",  # type: ignore[arg-type]
    )
    report = detect_divergence([a], [b], strict=True)
    assert not report.matched


# ---------- end-to-end: read jsonl from disk, replay, match ----------


def test_replay_from_disk_round_trip(tmp_path: Path) -> None:
    from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder

    suite = load_suite(TASKS_DIR)
    task = next(t for t in suite.tasks if t.name == "write_then_read")
    events = _capture_task_trace(task)

    trace_path = tmp_path / "trace.jsonl"
    recorder = JsonlTraceRecorder(trace_path)
    for e in events:
        recorder.record(e)

    loaded = read_trace(trace_path)
    replayed = replay_session(loaded)
    report = detect_divergence(loaded, replayed)
    assert report.matched, report.render()
