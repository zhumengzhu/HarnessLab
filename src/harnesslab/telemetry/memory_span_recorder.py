"""In-memory span recorder for tests and replay (Observability v2 O1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from harnesslab.core.contracts import ClockPort
from harnesslab.core.models import (
    SpanEventRecord,
    SpanHandle,
    SpanKind,
    SpanLinkRecord,
    SpanRecord,
    SpanStatus,
)
from harnesslab.core.runtime import SystemClock
from harnesslab.telemetry.span_attributes import HARNESSLAB_SESSION_ID, HARNESSLAB_TURN_INDEX
from harnesslab.telemetry.trace_ids import new_span_id


@dataclass
class _OpenSpan:
    handle: SpanHandle
    kind: SpanKind
    parent_span_id: str | None
    start_time: datetime
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEventRecord] = field(default_factory=list)
    links: list[SpanLinkRecord] = field(default_factory=list)


class MemorySpanRecorder:
    """Collect completed ``SpanRecord`` rows in memory."""

    def __init__(
        self,
        *,
        clock: ClockPort | None = None,
        resource: dict[str, Any] | None = None,
    ) -> None:
        self._clock: ClockPort = clock or SystemClock()
        self._resource = dict(resource or {})
        self._stacks: dict[str, list[_OpenSpan]] = {}
        self._open_by_id: dict[str, _OpenSpan] = {}
        self._completed: list[SpanRecord] = []

    @property
    def spans(self) -> list[SpanRecord]:
        return list(self._completed)

    def open_span_count(self, session_id: str | None = None) -> int:
        if session_id is None:
            return len(self._open_by_id)
        stack = self._stacks.get(session_id, [])
        return len(stack)

    def start_span(
        self,
        name: str,
        *,
        session_id: str,
        kind: SpanKind = "internal",
        attributes: dict[str, Any] | None = None,
        parent: SpanHandle | None = None,
        trace_id: str | None = None,
        turn_index: int | None = None,
    ) -> SpanHandle:
        attrs = dict(attributes or {})
        if parent is not None:
            resolved_trace_id = parent.trace_id
            resolved_turn = parent.turn_index
            parent_span_id = parent.span_id
        else:
            if trace_id is None or turn_index is None:
                msg = "trace_id and turn_index required when parent is None"
                raise ValueError(msg)
            resolved_trace_id = trace_id
            resolved_turn = turn_index
            parent_span_id = None

        span_id = new_span_id()
        handle = SpanHandle(
            trace_id=resolved_trace_id,
            span_id=span_id,
            session_id=session_id,
            turn_index=resolved_turn,
            name=name,
        )
        merged_attrs = {
            HARNESSLAB_SESSION_ID: session_id,
            HARNESSLAB_TURN_INDEX: resolved_turn,
            **attrs,
        }
        open_span = _OpenSpan(
            handle=handle,
            kind=kind,
            parent_span_id=parent_span_id,
            start_time=self._clock.now(),
            attributes=merged_attrs,
        )
        self._stacks.setdefault(session_id, []).append(open_span)
        self._open_by_id[span_id] = open_span
        return handle

    def end_span(
        self,
        handle: SpanHandle,
        *,
        status: SpanStatus = "ok",
        status_message: str | None = None,
        attributes: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> SpanRecord:
        open_span = self._pop_open(handle)
        if attributes:
            open_span.attributes.update(attributes)
        end_time = self._clock.now()
        duration_ms = max(0.0, (end_time - open_span.start_time).total_seconds() * 1000.0)
        record = SpanRecord(
            resource=dict(self._resource),
            trace_id=handle.trace_id,
            span_id=handle.span_id,
            parent_span_id=open_span.parent_span_id,
            name=handle.name,
            kind=open_span.kind,
            session_id=handle.session_id,
            turn_index=handle.turn_index,
            start_time=open_span.start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            status=status,
            status_message=status_message,
            attributes=dict(open_span.attributes),
            events=list(open_span.events),
            metrics=dict(metrics or {}),
            links=list(open_span.links),
        )
        self._completed.append(record)
        return record

    def add_span_event(
        self,
        handle: SpanHandle,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        open_span = self._require_open(handle)
        open_span.events.append(
            SpanEventRecord(
                name=name,
                time=self._clock.now(),
                attributes=dict(attributes or {}),
            )
        )

    def add_span_link(
        self,
        handle: SpanHandle,
        *,
        linked_trace_id: str,
        linked_span_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        open_span = self._require_open(handle)
        open_span.links.append(
            SpanLinkRecord(
                trace_id=linked_trace_id,
                span_id=linked_span_id,
                attributes=dict(attributes or {}),
            )
        )

    def current_span(self, session_id: str) -> SpanHandle | None:
        stack = self._stacks.get(session_id)
        if not stack:
            return None
        return stack[-1].handle

    def _require_open(self, handle: SpanHandle) -> _OpenSpan:
        open_span = self._open_by_id.get(handle.span_id)
        if open_span is None or open_span.handle.trace_id != handle.trace_id:
            msg = f"span not open: {handle.name!r} ({handle.span_id})"
            raise KeyError(msg)
        return open_span

    def _pop_open(self, handle: SpanHandle) -> _OpenSpan:
        open_span = self._require_open(handle)
        stack = self._stacks.get(handle.session_id, [])
        if not stack or stack[-1].handle.span_id != handle.span_id:
            msg = (
                f"span must close in LIFO order for session {handle.session_id}: "
                f"expected {stack[-1].handle.name if stack else '?'}, got {handle.name}"
            )
            raise RuntimeError(msg)
        stack.pop()
        if not stack:
            self._stacks.pop(handle.session_id, None)
        self._open_by_id.pop(handle.span_id, None)
        return open_span


def default_test_resource() -> dict[str, str]:
    return {
        "service.name": "harnesslab",
        "service.version": "0.1.0",
        "service.instance.id": "test:1",
        "deployment.environment": "local",
        "harnesslab.workspace": "test",
    }
