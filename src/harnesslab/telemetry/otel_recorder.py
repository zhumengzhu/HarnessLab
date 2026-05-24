"""OpenTelemetry fan-out adapter for TraceRecorderPort (Post-MVP P7)."""

from __future__ import annotations

import os
from typing import Any

from harnesslab.core.contracts import TraceRecorderPort
from harnesslab.core.models import TraceEvent

_VOLATILE_PAYLOAD_KEYS = frozenset(
    {
        "latency_ms",
        "request_tokens",
        "response_tokens",
        "total_tokens",
        "reasoning_tokens",
        "model_name",
        "provider",
        "api_family",
        "trace_id",
        "span_id",
    }
)


class OtelTraceRecorder:
    """Record to an inner port and emit OpenTelemetry spans when enabled."""

    def __init__(
        self,
        inner: TraceRecorderPort,
        *,
        enabled: bool | None = None,
        tracer: Any | None = None,
    ) -> None:
        self._inner = inner
        self._enabled = _resolve_enabled(enabled)
        self._tracer = tracer
        if self._enabled and self._tracer is None:
            self._tracer = _default_tracer()

    def record(self, event: TraceEvent) -> None:
        self._inner.record(event)
        if not self._enabled or self._tracer is None:
            return
        attrs = _span_attributes(event)
        span_name = f"harnesslab.{event.event_type}"
        with self._tracer.start_as_current_span(span_name, attributes=attrs):
            pass


def wrap_trace_recorder(
    inner: TraceRecorderPort,
    *,
    enabled: bool | None = None,
    tracer: Any | None = None,
) -> TraceRecorderPort:
    """Return ``inner`` or an OTel fan-out wrapper when enabled."""

    if not _resolve_enabled(enabled):
        return inner
    return OtelTraceRecorder(inner, enabled=True, tracer=tracer)


def _resolve_enabled(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    if os.environ.get("HARNESSLAB_OTEL", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())


def _default_tracer() -> Any:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": "harnesslab"})
    provider = TracerProvider(resource=resource)
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("harnesslab")


def _span_attributes(event: TraceEvent) -> dict[str, str | int | float | bool]:
    attrs: dict[str, str | int | float | bool] = {
        "harnesslab.run_id": event.run_id,
        "harnesslab.session_id": event.session_id,
        "harnesslab.event_type": event.event_type,
    }
    for key, value in event.payload.items():
        if key in _VOLATILE_PAYLOAD_KEYS:
            continue
        normalized = _normalize_attribute(key, value)
        if normalized is not None:
            attr_key, attr_value = normalized
            attrs[attr_key] = attr_value
    return attrs


def _normalize_attribute(
    key: str,
    value: Any,
) -> tuple[str, str | int | float | bool] | None:
    attr_key = f"harnesslab.payload.{key}"
    if isinstance(value, (str, int, float, bool)):
        return attr_key, value
    if value is None:
        return None
    return attr_key, str(value)
