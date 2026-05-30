"""Context manager for span lifecycle instrumentation (Observability v2 O1)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from harnesslab.core.contracts import SpanRecorderPort
from harnesslab.core.models import Session, SpanHandle, SpanKind
from harnesslab.telemetry.span_attributes import HARNESSLAB_TURN_INDEX
from harnesslab.telemetry.trace_ids import new_trace_id


@contextmanager
def trace_scope(
    recorder: SpanRecorderPort,
    name: str,
    *,
    session_id: str,
    kind: SpanKind = "internal",
    attributes: dict[str, Any] | None = None,
    parent: SpanHandle | None = None,
    turn_index: int | None = None,
    is_trace_root: bool = False,
) -> Iterator[SpanHandle]:
    """Start/end a span with exception-safe ``end_span``.

    Normative requirements: ``docs/architecture/observability-v2.md`` § D4.
    """

    if is_trace_root:
        if parent is not None:
            raise ValueError("trace root span must not have an explicit parent")
        if turn_index is None:
            raise ValueError("turn_index is required when is_trace_root=True")
        handle = recorder.start_span(
            name,
            session_id=session_id,
            kind=kind,
            attributes=attributes,
            parent=None,
            trace_id=new_trace_id(),
            turn_index=turn_index,
        )
    else:
        resolved_parent = parent if parent is not None else recorder.current_span(session_id)
        if resolved_parent is None:
            msg = f"no parent span for {name!r} in session {session_id}"
            raise ValueError(msg)
        handle = recorder.start_span(
            name,
            session_id=session_id,
            kind=kind,
            attributes=attributes,
            parent=resolved_parent,
        )

    try:
        yield handle
    except Exception as exc:
        recorder.end_span(handle, status="error", status_message=str(exc))
        raise
    else:
        recorder.end_span(handle)


@contextmanager
def trace_scope_for_session(
    recorder: SpanRecorderPort,
    name: str,
    session: Session,
    *,
    kind: SpanKind = "internal",
    attributes: dict[str, Any] | None = None,
    parent: SpanHandle | None = None,
    turn_index: int | None = None,
    is_trace_root: bool = False,
) -> Iterator[SpanHandle]:
    """Like :func:`trace_scope` but binds ``session_id`` from a ``Session``."""

    merged = dict(attributes or {})
    if is_trace_root and turn_index is not None:
        merged.setdefault(HARNESSLAB_TURN_INDEX, turn_index)
    with trace_scope(
        recorder,
        name,
        session_id=session.id,
        kind=kind,
        attributes=merged or None,
        parent=parent,
        turn_index=turn_index,
        is_trace_root=is_trace_root,
    ) as handle:
        yield handle
