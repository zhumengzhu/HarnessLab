"""Tests for OpenTelemetry trace fan-out (Post-MVP P7)."""

from __future__ import annotations

from datetime import UTC, datetime

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from harnesslab.core.models import TraceEvent
from harnesslab.core.replay import ReplayTraceRecorder
from harnesslab.telemetry.otel_recorder import OtelTraceRecorder, wrap_trace_recorder


def test_wrap_trace_recorder_disabled_by_default() -> None:
    inner = ReplayTraceRecorder()
    wrapped = wrap_trace_recorder(inner, enabled=False)
    assert wrapped is inner


def test_otel_recorder_fan_out_records_spans() -> None:
    inner = ReplayTraceRecorder()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("harnesslab-test")
    recorder = OtelTraceRecorder(inner, enabled=True, tracer=tracer)
    event = TraceEvent(
        run_id="run_1",
        session_id="ses_1",
        event_type="model_call",
        payload={"decision_kind": "final", "request_tokens": 10},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    recorder.record(event)
    assert len(inner.events) == 1
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "harnesslab.model_call"
    attrs = dict(spans[0].attributes or {})
    assert attrs["harnesslab.session_id"] == "ses_1"
    assert attrs["harnesslab.payload.decision_kind"] == "final"
    assert "harnesslab.payload.request_tokens" not in attrs
