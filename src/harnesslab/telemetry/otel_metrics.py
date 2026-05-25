"""OpenTelemetry metrics fan-out from trace events (Phase 5.6)."""

from __future__ import annotations

import os
from typing import Any

from harnesslab.core.contracts import TraceRecorderPort
from harnesslab.core.models import TraceEvent
from harnesslab.telemetry.otel_recorder import _resolve_enabled


class OtelMetricsRecorder:
    """Record metrics instruments from the same TraceEvent stream as spans."""

    def __init__(
        self,
        inner: TraceRecorderPort,
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
        self._session_steps = None
        if self._enabled:
            self._init_instruments(meter)

    def _init_instruments(self, meter: Any | None) -> None:
        if meter is None:
            meter = _default_meter()
        self._meter = meter
        self._model_latency = meter.create_histogram(
            "harnesslab.model.latency_ms",
            unit="ms",
            description="Model call latency",
        )
        self._model_tokens = meter.create_counter(
            "harnesslab.model.tokens.total",
            description="Total model tokens",
        )
        self._tool_duration = meter.create_histogram(
            "harnesslab.tool.duration_ms",
            unit="ms",
            description="Tool execution duration",
        )
        self._session_steps = meter.create_histogram(
            "harnesslab.session.steps",
            description="Steps per session turn",
        )

    def record(self, event: TraceEvent) -> None:
        self._inner.record(event)
        if not self._enabled or self._meter is None:
            return
        payload = event.payload
        if event.event_type == "model_call":
            attrs = {
                "provider": str(payload.get("provider", "unknown")),
                "api_family": str(payload.get("api_family", "unknown")),
                "decision_kind": str(payload.get("decision_kind", "unknown")),
            }
            latency = payload.get("latency_ms")
            if isinstance(latency, (int, float)) and self._model_latency is not None:
                self._model_latency.record(float(latency), attributes=attrs)
            total = payload.get("total_tokens")
            if isinstance(total, int) and self._model_tokens is not None:
                self._model_tokens.add(total, attributes=attrs)
        elif event.event_type == "tool_executed":
            attrs = {
                "tool": str(payload.get("tool", "unknown")),
                "ok": bool(payload.get("ok", False)),
            }
            duration = payload.get("duration_ms")
            if isinstance(duration, (int, float)) and self._tool_duration is not None:
                self._tool_duration.record(float(duration), attributes=attrs)
        elif event.event_type == "turn_completed":
            steps = payload.get("steps_used")
            if isinstance(steps, int) and self._session_steps is not None:
                self._session_steps.record(steps)


def wrap_trace_recorder_with_metrics(
    inner: TraceRecorderPort,
    *,
    enabled: bool | None = None,
    meter: Any | None = None,
) -> TraceRecorderPort:
    if not _resolve_enabled(enabled):
        return inner
    return OtelMetricsRecorder(inner, enabled=True, meter=meter)


def _default_meter() -> Any:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": "harnesslab"})
    provider = MeterProvider(resource=resource)
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return metrics.get_meter("harnesslab")
