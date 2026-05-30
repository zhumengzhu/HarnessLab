"""OpenTelemetry lifecycle export for completed spans (Observability v2 O4)."""

from __future__ import annotations

import os
from typing import Any

from harnesslab.core.contracts import SpanRecorderPort
from harnesslab.core.models import SpanHandle, SpanKind, SpanRecord, SpanStatus


class OtelExportingRecorder:
    """Delegate span port and export completed spans to OTel."""

    def __init__(
        self,
        inner: SpanRecorderPort,
        *,
        tracer: Any | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._inner = inner
        self._enabled = _resolve_enabled(enabled)
        self._tracer = tracer
        self._active: dict[str, Any] = {}
        if self._enabled and self._tracer is None:
            self._tracer = _default_tracer()

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
        if self._enabled and self._tracer is not None:
            otel_span = self._tracer.start_span(
                name,
                start_time=_otel_time(handle),
                attributes=_otel_attributes(attributes),
            )
            self._active[handle.span_id] = otel_span
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
        if self._enabled:
            otel_span = self._active.pop(handle.span_id, None)
            if otel_span is not None:
                if attributes:
                    for key, value in _otel_attributes(attributes).items():
                        otel_span.set_attribute(key, value)
                if status == "error":
                    otel_span.set_status(
                        _otel_status_error(),
                        status_message or "error",
                    )
                otel_span.end(end_time=_otel_ns(record.end_time))
        return record

    def add_span_event(
        self,
        handle: SpanHandle,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._inner.add_span_event(handle, name, attributes=attributes)
        if self._enabled:
            otel_span = self._active.get(handle.span_id)
            if otel_span is not None:
                otel_span.add_event(name, attributes=_otel_attributes(attributes))

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

    def current_span(self, session_id: str) -> SpanHandle | None:
        return self._inner.current_span(session_id)


def attach_otel_export(
    inner: SpanRecorderPort,
    *,
    resource: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> SpanRecorderPort:
    if not _resolve_enabled(enabled):
        return inner
    tracer = _default_tracer(resource=resource)
    return OtelExportingRecorder(inner, enabled=True, tracer=tracer)


def _resolve_enabled(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    if os.environ.get("HARNESSLAB_OTEL", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())


def _default_tracer(*, resource: dict[str, Any] | None = None) -> Any:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource_attrs = dict(resource or {})
    resource_attrs.setdefault("service.name", "harnesslab")
    provider = TracerProvider(resource=Resource.create(resource_attrs))
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    if os.environ.get("HARNESSLAB_OTEL_CONSOLE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("harnesslab")


def _otel_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    if not attributes:
        return {}
    normalized: dict[str, Any] = {}
    for key, value in attributes.items():
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        elif value is not None:
            normalized[key] = str(value)
    return normalized


def _otel_ns(dt: Any) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def _otel_time(handle: SpanHandle) -> int | None:
    return None


def _otel_status_error() -> Any:
    from opentelemetry.trace import StatusCode

    return StatusCode.ERROR
