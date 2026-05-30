"""OpenTelemetry metrics from completed spans (Observability v2 O4)."""

from __future__ import annotations

import os
from typing import Any

from harnesslab.core.contracts import SpanRecorderPort
from harnesslab.core.models import SpanHandle, SpanKind, SpanRecord, SpanStatus
from harnesslab.telemetry.span_attributes import SPAN_LLM_GENERATE, SPAN_TURN


class SpanMetricsRecorder:
    """Delegate span port and emit OTel metrics on completed spans."""

    def __init__(
        self,
        inner: SpanRecorderPort,
        *,
        enabled: bool | None = None,
        meter: Any | None = None,
    ) -> None:
        self._inner = inner
        self._enabled = _resolve_enabled(enabled)
        self._meter = meter
        self._model_latency = None
        self._model_tokens = None
        self._tool_duration = None
        self._turn_wall = None
        if self._enabled:
            if self._meter is None:
                self._meter = _default_meter()
            self._init_instruments(self._meter)

    def _init_instruments(self, meter: Any | None) -> None:
        if meter is None:
            return
        self._model_latency = meter.create_histogram(
            "harnesslab.model.latency_ms",
            unit="ms",
            description="Model call latency",
        )
        self._model_tokens = meter.create_counter(
            "harnesslab.model.tokens.total",
            unit="token",
            description="Total model tokens",
        )
        self._tool_duration = meter.create_histogram(
            "harnesslab.tool.duration_ms",
            unit="ms",
            description="Tool execute duration",
        )
        self._turn_wall = meter.create_histogram(
            "harnesslab.turn.wall_ms",
            unit="ms",
            description="Turn wall time",
        )

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
        return self._inner.start_span(
            name,
            session_id=session_id,
            kind=kind,
            attributes=attributes,
            parent=parent,
            trace_id=trace_id,
            turn_index=turn_index,
        )

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
            self._record_metrics(record)
        return record

    def add_span_event(
        self,
        handle: SpanHandle,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._inner.add_span_event(handle, name, attributes=attributes)

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

    def _record_metrics(self, record: SpanRecord) -> None:
        attrs = {
            key: str(value)
            for key, value in record.attributes.items()
            if isinstance(value, (str, int, float, bool))
        }
        metrics = record.metrics
        if record.name == SPAN_LLM_GENERATE:
            latency = metrics.get("latency_ms")
            if isinstance(latency, (int, float)) and self._model_latency is not None:
                self._model_latency.record(float(latency), attributes=attrs)
            total = metrics.get("total_tokens")
            if isinstance(total, int) and self._model_tokens is not None:
                self._model_tokens.add(total, attributes=attrs)
        elif record.name.startswith("tool.execute") or record.name.startswith("tool."):
            duration = metrics.get("duration_ms", record.duration_ms)
            if isinstance(duration, (int, float)) and self._tool_duration is not None:
                self._tool_duration.record(float(duration), attributes=attrs)
        elif record.name == SPAN_TURN and self._turn_wall is not None:
            self._turn_wall.record(float(record.duration_ms), attributes=attrs)


def attach_span_metrics(
    inner: SpanRecorderPort,
    *,
    enabled: bool | None = None,
    meter: Any | None = None,
) -> SpanRecorderPort:
    if not _resolve_enabled(enabled):
        return inner
    return SpanMetricsRecorder(inner, enabled=True, meter=meter)


def _resolve_enabled(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    if os.environ.get("HARNESSLAB_OTEL", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())


def _default_meter() -> Any:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": "harnesslab"})
    readers = []
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(),
            )
        )
    provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(provider)
    return metrics.get_meter("harnesslab")
