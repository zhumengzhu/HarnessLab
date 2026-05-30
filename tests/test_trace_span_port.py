"""Contract tests for Observability v2 span port (O1)."""

from __future__ import annotations

import pytest

from harnesslab.core.contracts import SpanRecorderPort
from harnesslab.core.models import Session
from harnesslab.core.replay import ReplaySpanRecorder
from harnesslab.core.runtime import SystemClock
from harnesslab.core.trace_scope import trace_scope, trace_scope_for_session
from harnesslab.telemetry.memory_span_recorder import MemorySpanRecorder, default_test_resource
from harnesslab.telemetry.span_attributes import (
    HARNESSLAB_SESSION_ID,
    HARNESSLAB_TURN_INDEX,
    SPAN_LLM_GENERATE,
    SPAN_STEP,
    SPAN_TURN,
)


@pytest.fixture
def recorder() -> MemorySpanRecorder:
    return MemorySpanRecorder(clock=SystemClock(), resource=default_test_resource())


def test_span_recorder_port_structural(recorder: MemorySpanRecorder) -> None:
    port: SpanRecorderPort = recorder
    handle = port.start_span(
        SPAN_TURN,
        session_id="ses_a",
        trace_id="a" * 32,
        turn_index=0,
    )
    record = port.end_span(handle)
    assert record.name == SPAN_TURN
    assert record.session_id == "ses_a"


def test_trace_root_allocates_trace_id(recorder: MemorySpanRecorder) -> None:
    with trace_scope(
        recorder,
        SPAN_TURN,
        session_id="ses_a",
        turn_index=0,
        is_trace_root=True,
    ) as turn:
        trace_id = turn.trace_id
        with trace_scope(recorder, SPAN_STEP, session_id="ses_a", parent=turn) as step:
            assert step.trace_id == trace_id
            assert step.turn_index == 0
    assert len(recorder.spans) == 2
    by_name = {span.name: span for span in recorder.spans}
    turn_record = by_name[SPAN_TURN]
    step_record = by_name[SPAN_STEP]
    assert turn_record.parent_span_id is None
    assert step_record.parent_span_id == turn_record.span_id


def test_child_inherits_turn_index(recorder: MemorySpanRecorder) -> None:
    with trace_scope(
        recorder,
        SPAN_TURN,
        session_id="ses_a",
        turn_index=3,
        is_trace_root=True,
    ) as turn:
        with trace_scope(recorder, SPAN_LLM_GENERATE, session_id="ses_a", kind="client") as llm:
            assert llm.turn_index == 3
            attrs = recorder.spans  # none completed yet
            assert attrs == []
            assert llm.trace_id == turn.trace_id
    completed = recorder.spans
    assert completed[1].attributes[HARNESSLAB_TURN_INDEX] == 3


def test_explicit_parent_for_compact_under_turn(recorder: MemorySpanRecorder) -> None:
    with trace_scope(
        recorder,
        SPAN_TURN,
        session_id="ses_a",
        turn_index=0,
        is_trace_root=True,
    ) as turn:
        with trace_scope(
            recorder,
            "context.compact",
            session_id="ses_a",
            parent=turn,
            attributes={"harnesslab.compaction.trigger": "manual"},
        ):
            pass
    by_name = {span.name: span for span in recorder.spans}
    compact = by_name["context.compact"]
    turn_record = by_name[SPAN_TURN]
    assert compact.parent_span_id == turn_record.span_id
    assert compact.attributes["harnesslab.compaction.trigger"] == "manual"


def test_exception_marks_span_error(recorder: MemorySpanRecorder) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with trace_scope(
            recorder,
            SPAN_TURN,
            session_id="ses_a",
            turn_index=0,
            is_trace_root=True,
        ):
            raise RuntimeError("boom")
    assert recorder.spans[0].status == "error"
    assert recorder.spans[0].status_message == "boom"
    assert recorder.open_span_count() == 0


def test_session_stacks_are_isolated(recorder: MemorySpanRecorder) -> None:
    with trace_scope(
        recorder,
        SPAN_TURN,
        session_id="ses_a",
        turn_index=0,
        is_trace_root=True,
    ):
        with trace_scope(
            recorder,
            SPAN_TURN,
            session_id="ses_b",
            turn_index=0,
            is_trace_root=True,
        ):
            assert recorder.current_span("ses_a") is not None
            assert recorder.current_span("ses_b") is not None
            assert recorder.current_span("ses_a") != recorder.current_span("ses_b")
    assert recorder.open_span_count() == 0


def test_span_event_and_link(recorder: MemorySpanRecorder) -> None:
    with trace_scope(
        recorder,
        SPAN_TURN,
        session_id="ses_a",
        turn_index=0,
        is_trace_root=True,
    ) as turn:
        recorder.add_span_event(turn, "budget.soft_threshold", {"dimension": "tokens"})
        recorder.add_span_link(
            turn,
            linked_trace_id="b" * 32,
            linked_span_id="c" * 16,
            attributes={"harnesslab.link.kind": "sub_agent"},
        )
    record = recorder.spans[0]
    assert len(record.events) == 1
    assert record.events[0].name == "budget.soft_threshold"
    assert len(record.links) == 1
    assert record.links[0].trace_id == "b" * 32


def test_completion_order_is_lifo(recorder: MemorySpanRecorder) -> None:
    with trace_scope(
        recorder,
        SPAN_TURN,
        session_id="ses_a",
        turn_index=0,
        is_trace_root=True,
    ) as turn:
        with trace_scope(recorder, SPAN_STEP, session_id="ses_a", parent=turn):
            with trace_scope(recorder, SPAN_LLM_GENERATE, session_id="ses_a", kind="client"):
                pass
    names = [span.name for span in recorder.spans]
    assert names == [SPAN_LLM_GENERATE, SPAN_STEP, SPAN_TURN]


def test_out_of_order_end_raises(recorder: MemorySpanRecorder) -> None:
    turn = recorder.start_span(
        SPAN_TURN,
        session_id="ses_a",
        trace_id="d" * 32,
        turn_index=0,
    )
    step = recorder.start_span(SPAN_STEP, session_id="ses_a", parent=turn)
    with pytest.raises(RuntimeError, match="LIFO"):
        recorder.end_span(turn)
    recorder.end_span(step)
    recorder.end_span(turn)


def test_trace_scope_for_session(recorder: MemorySpanRecorder) -> None:
    session = Session(goal="hello")
    with trace_scope_for_session(
        recorder,
        SPAN_TURN,
        session,
        turn_index=0,
        is_trace_root=True,
    ) as turn:
        assert turn.session_id == session.id
    assert recorder.spans[0].attributes[HARNESSLAB_SESSION_ID] == session.id


def test_replay_span_recorder_alias() -> None:
    replay = ReplaySpanRecorder(resource=default_test_resource())
    with trace_scope(replay, SPAN_TURN, session_id="ses_x", turn_index=0, is_trace_root=True):
        pass
    assert len(replay.spans) == 1
