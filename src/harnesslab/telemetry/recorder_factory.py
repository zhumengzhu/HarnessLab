"""Build the default span recorder chain for CLI / serve."""

from __future__ import annotations

import os
from pathlib import Path

from harnesslab.core.contracts import SpanRecorderPort
from harnesslab.telemetry.local_span_recorder import LocalSpanRecorder
from harnesslab.telemetry.otel_metrics import attach_span_metrics
from harnesslab.telemetry.otel_span_recorder import attach_otel_export
from harnesslab.telemetry.process_resource import build_process_resource


def default_spans_path(workspace_root: Path) -> Path:
    return workspace_root / ".harnesslab" / "spans.jsonl"


def build_span_recorder(
    workspace_root: Path,
    *,
    spans_path: Path | None = None,
    otel_enabled: bool | None = None,
) -> SpanRecorderPort:
    """Return local JSONL recorder with optional OTLP + metrics fan-out."""

    path = spans_path or default_spans_path(workspace_root)
    resource = build_process_resource(workspace_root)
    recorder: SpanRecorderPort = LocalSpanRecorder(path, resource=resource)
    if _resolve_otel_enabled(otel_enabled):
        recorder = attach_otel_export(recorder, resource=resource)
        recorder = attach_span_metrics(recorder)
    return recorder


def _resolve_otel_enabled(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    if os.environ.get("HARNESSLAB_OTEL", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())
