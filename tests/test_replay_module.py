"""Tests for the Step 5 replay subsystem (Observability v2 spans)."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import pytest

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import SpanRecord
from harnesslab.core.replay import ReplayModel, ReplaySpanRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.eval.loader import load_suite
from harnesslab.eval.runner import _build_tool_registry, _limits_for_task
from harnesslab.eval.task import Task
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.replay import (
    UnreplayableTraceError,
    child_session_ids_for_parent,
    detect_divergence,
    group_by_session,
    read_spans,
    replay_session,
)
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.span_attributes import SPAN_TURN

TASKS_DIR = Path(__file__).resolve().parents[1] / "eval" / "tasks"


def _capture_task_spans(task: Task) -> tuple[list[SpanRecord], Path]:
    """Drive a task end-to-end; return spans and workspace path."""

    workspace = Path(tempfile.mkdtemp(prefix="hl-replay-spans-"))
    limits = _limits_for_task(task)
    tools = _build_tool_registry(workspace, limits)
    recorder = ReplaySpanRecorder()
    model = ReplayModel(decisions=task.decisions) if task.decisions else SimpleModel()
    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(
            workspace_root=workspace,
            shell_profile=(
                task.policy.shell_profile if task.policy is not None else None
            ),
        ),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        limits=limits,
        memory=InMemoryMemoryStore(),
        workspace_root=workspace,
    )
    session = loop.start(goal=task.goal)
    current_id = session.id
    for turn in task.turns:
        if turn.new_session:
            session = loop.start(goal=turn.goal or task.goal)
            current_id = session.id
        loop.run_session(current_id, turn.input, max_steps=turn.max_steps)
    return recorder.spans, workspace


# ---------- span_reader ----------


def test_read_spans_parses_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    span = SpanRecord(
        trace_id="a" * 32,
        span_id="b" * 16,
        name=SPAN_TURN,
        session_id="ses_000001",
        turn_index=0,
        start_time="2026-01-01T00:00:00+00:00",  # type: ignore[arg-type]
        end_time="2026-01-01T00:00:01+00:00",  # type: ignore[arg-type]
        duration_ms=1.0,
    )
    path.write_text(span.model_dump_json() + "\n", encoding="utf-8")
    spans = read_spans(path)
    assert len(spans) == 1
    assert spans[0].name == SPAN_TURN


def test_read_spans_rejects_malformed_line(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_spans(path)


def test_group_by_session_preserves_order() -> None:
    def span(sid: str, name: str) -> SpanRecord:
        return SpanRecord(
            trace_id="t" * 32,
            span_id=f"span_{name}_{sid}",
            name=name,
            session_id=sid,
            turn_index=0,
            start_time="2026-01-01T00:00:00+00:00",  # type: ignore[arg-type]
            end_time="2026-01-01T00:00:01+00:00",  # type: ignore[arg-type]
            duration_ms=1.0,
        )

    spans = [span("s1", "a"), span("s2", "a"), span("s1", "b")]
    grouped = group_by_session(spans)
    assert list(grouped.keys()) == ["s1", "s2"]
    assert [s.name for s in grouped["s1"]] == ["a", "b"]


def test_child_session_ids_for_parent_follows_span_order() -> None:
    parent_id = "ses_parent"
    child_a = "ses_child_a"
    child_b = "ses_child_b"
    base = {
        "trace_id": "t" * 32,
        "span_id": "s" * 16,
        "turn_index": 0,
        "start_time": "2026-01-01T00:00:00+00:00",  # type: ignore[arg-type]
        "end_time": "2026-01-01T00:00:01+00:00",  # type: ignore[arg-type]
        "duration_ms": 1.0,
    }
    spans = [
        SpanRecord(
            **base,
            name="sub_agent.run",
            session_id=parent_id,
            attributes={"harnesslab.child_session.id": child_b},
        ),
        SpanRecord(
            **base,
            name=SPAN_TURN,
            session_id=child_a,
            attributes={"harnesslab.parent_session.id": parent_id},
        ),
        SpanRecord(
            **base,
            name="sub_agent.run",
            session_id=parent_id,
            attributes={"harnesslab.child_session.id": child_a},
        ),
    ]
    assert child_session_ids_for_parent(spans, parent_id) == [child_b, child_a]


# ---------- replayer happy path against real eval traces ----------


def test_replay_matches_eval_task_traces() -> None:
    suite = load_suite(TASKS_DIR)
    for task in suite.tasks:
        original, workspace = _capture_task_spans(task)
        replayed = replay_session(original, workspace_root=workspace)
        report = detect_divergence(original, replayed)
        assert report.matched, (
            f"{task.name} diverged after replay:\n{report.render()}"
        )


def test_replay_round_trips_multi_step_turn() -> None:
    suite = load_suite(TASKS_DIR)
    task = next(t for t in suite.tasks if t.name == "multi_step_tool_then_final")
    original, workspace = _capture_task_spans(task)

    llm_spans = [s for s in original if s.name == "llm.generate"]
    turn_spans = [s for s in original if s.name == SPAN_TURN]
    assert len(turn_spans) == 1
    assert len(llm_spans) == 2

    replayed = replay_session(original, workspace_root=workspace)
    report = detect_divergence(original, replayed)
    assert report.matched, report.render()


def test_replay_empty_trace_raises() -> None:
    with pytest.raises(UnreplayableTraceError):
        replay_session([])


# ---------- divergence: tampering must be detected ----------


def _eval_spans_for(task_name: str) -> list[SpanRecord]:
    suite = load_suite(TASKS_DIR)
    task = next(t for t in suite.tasks if t.name == task_name)
    return _capture_task_spans(task)[0]


def test_divergence_detects_tampered_decision() -> None:
    original = _eval_spans_for("write_then_read")
    tampered = copy.deepcopy(original)
    for span in tampered:
        for event in span.events:
            if (
                event.name == "decision.applied"
                and event.attributes.get("tool_name") == "write_file"
            ):
                event.attributes["tool_name"] = "read_file"
                break
    replayed = replay_session(tampered)
    report = detect_divergence(original, replayed)
    assert not report.matched


def test_divergence_detects_extra_span() -> None:
    original = _eval_spans_for("assistant_fallback")
    extra = original[0].model_copy(
        update={"span_id": "extra_span_id_001", "name": "extra.span"}
    )
    replayed = list(original) + [extra]
    report = detect_divergence(original, replayed)
    assert not report.matched
    assert any(d.kind == "length_mismatch" for d in report.divergences)


def test_divergence_ignores_id_renaming() -> None:
    base = SpanRecord(
        trace_id="trace_aaa" + "0" * 24,
        span_id="span_aaa" + "0" * 8,
        name="tool.read_file",
        session_id="ses_aaa",
        turn_index=0,
        start_time="2026-01-01T00:00:00+00:00",  # type: ignore[arg-type]
        end_time="2026-01-01T00:00:01+00:00",  # type: ignore[arg-type]
        duration_ms=1.0,
        attributes={"harnesslab.tool_call.id": "tool_aaa"},
    )
    renamed = base.model_copy(
        update={
            "trace_id": "trace_xyz" + "0" * 24,
            "span_id": "span_xyz" + "0" * 8,
            "session_id": "ses_xyz",
            "attributes": {"harnesslab.tool_call.id": "tool_xyz"},
        }
    )
    report = detect_divergence([base], [renamed])
    assert report.matched, report.render()


def test_divergence_strict_mode_flags_timing_diff() -> None:
    a = SpanRecord(
        trace_id="t" * 32,
        span_id="a" * 16,
        name=SPAN_TURN,
        session_id="ses_a",
        turn_index=0,
        start_time="2026-01-01T00:00:00+00:00",  # type: ignore[arg-type]
        end_time="2026-01-01T00:00:01+00:00",  # type: ignore[arg-type]
        duration_ms=1.0,
    )
    b = a.model_copy(
        update={
            "start_time": "2030-12-31T23:59:58+00:00",  # type: ignore[arg-type]
            "end_time": "2030-12-31T23:59:59+00:00",  # type: ignore[arg-type]
        }
    )
    report = detect_divergence([a], [b], strict=True)
    assert not report.matched


# ---------- end-to-end: read jsonl from disk, replay, match ----------


def test_replay_from_disk_round_trip(tmp_path: Path) -> None:
    suite = load_suite(TASKS_DIR)
    task = next(t for t in suite.tasks if t.name == "write_then_read")
    spans, workspace = _capture_task_spans(task)

    spans_path = tmp_path / "spans.jsonl"
    spans_path.write_text(
        "\n".join(span.model_dump_json() for span in spans) + "\n",
        encoding="utf-8",
    )

    loaded = read_spans(spans_path)
    replayed = replay_session(loaded, workspace_root=workspace)
    report = detect_divergence(spans, replayed)
    assert report.matched, report.render()
