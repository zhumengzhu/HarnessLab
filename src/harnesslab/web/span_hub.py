"""Fan-out span lifecycle events to SSE subscribers (Observability v2 O6)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from harnesslab.core.contracts import SpanRecorderPort
from harnesslab.core.models import SpanHandle, SpanKind, SpanRecord, SpanStatus

SpanStartedCallback = Callable[[dict[str, Any]], None]
SpanEventCallback = Callable[[dict[str, Any]], None]
SpanCompletedCallback = Callable[[SpanRecord], None]
SpanLinkCallback = Callable[[dict[str, Any]], None]


class SpanHub:
    """Wrap a ``SpanRecorderPort`` and notify subscribers on span lifecycle."""

    def __init__(self, inner: SpanRecorderPort) -> None:
        self._inner = inner
        self._started: list[SpanStartedCallback] = []
        self._events: list[SpanEventCallback] = []
        self._completed: list[SpanCompletedCallback] = []
        self._links: list[SpanLinkCallback] = []

    @property
    def inner(self) -> SpanRecorderPort:
        return self._inner

    def subscribe_started(self, callback: SpanStartedCallback) -> None:
        self._started.append(callback)

    def subscribe_event(self, callback: SpanEventCallback) -> None:
        self._events.append(callback)

    def subscribe_completed(self, callback: SpanCompletedCallback) -> None:
        self._completed.append(callback)

    def subscribe_link(self, callback: SpanLinkCallback) -> None:
        self._links.append(callback)

    def unsubscribe_started(self, callback: SpanStartedCallback) -> None:
        self._started = [item for item in self._started if item is not callback]

    def unsubscribe_event(self, callback: SpanEventCallback) -> None:
        self._events = [item for item in self._events if item is not callback]

    def unsubscribe_completed(self, callback: SpanCompletedCallback) -> None:
        self._completed = [item for item in self._completed if item is not callback]

    def unsubscribe_link(self, callback: SpanLinkCallback) -> None:
        self._links = [item for item in self._links if item is not callback]

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
        handle = self._inner.start_span(
            name,
            session_id=session_id,
            kind=kind,
            attributes=attributes,
            parent=parent,
            trace_id=trace_id,
            turn_index=turn_index,
        )
        payload = {
            "trace_id": handle.trace_id,
            "span_id": handle.span_id,
            "parent_span_id": parent.span_id if parent is not None else None,
            "name": name,
            "kind": kind,
            "session_id": session_id,
            "turn_index": handle.turn_index,
            "attributes": dict(attributes or {}),
        }
        for callback in self._started:
            callback(payload)
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
        record = self._inner.end_span(
            handle,
            status=status,
            status_message=status_message,
            attributes=attributes,
            metrics=metrics,
        )
        for callback in self._completed:
            callback(record)
        return record

    def add_span_event(
        self,
        handle: SpanHandle,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._inner.add_span_event(handle, name, attributes=attributes)
        payload = {
            "trace_id": handle.trace_id,
            "span_id": handle.span_id,
            "name": name,
            "attributes": dict(attributes or {}),
        }
        for callback in self._events:
            callback(payload)

    def add_span_link(
        self,
        handle: SpanHandle,
        *,
        linked_trace_id: str,
        linked_span_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._inner.add_span_link(
            handle,
            linked_trace_id=linked_trace_id,
            linked_span_id=linked_span_id,
            attributes=attributes,
        )
        payload = {
            "trace_id": handle.trace_id,
            "span_id": handle.span_id,
            "linked_trace_id": linked_trace_id,
            "linked_span_id": linked_span_id,
            "attributes": dict(attributes or {}),
        }
        for callback in self._links:
            callback(payload)

    def current_span(self, session_id: str) -> SpanHandle | None:
        return self._inner.current_span(session_id)
