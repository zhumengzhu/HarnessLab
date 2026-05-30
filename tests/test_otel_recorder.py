"""Tests for OpenTelemetry trace fan-out (Post-MVP P7, Observability v2)."""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from harnesslab.core.replay import ReplaySpanRecorder
from harnesslab.telemetry.otel_span_recorder import OtelExportingRecorder, attach_otel_export


def test_attach_otel_export_disabled_by_default() -> None:
    inner = ReplaySpanRecorder()
    wrapped = attach_otel_export(inner, enabled=False)
    assert wrapped is inner


def test_otel_span_recorder_fan_out_records_spans() -> None:
    inner = ReplaySpanRecorder()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("harnesslab-test")
    recorder = OtelExportingRecorder(inner, enabled=True, tracer=tracer)
    handle = recorder.start_span(
        "llm.generate",
        session_id="ses_1",
        trace_id="a" * 32,
        turn_index=0,
        kind="client",
    )
    recorder.end_span(handle, attributes={"harnesslab.decision.kind": "final"})
    assert len(inner.spans) == 1
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "llm.generate"
