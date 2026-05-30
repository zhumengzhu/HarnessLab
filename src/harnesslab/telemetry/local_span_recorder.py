"""Append completed spans to ``spans.jsonl`` (Observability v2 O2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harnesslab.core.contracts import ClockPort
from harnesslab.core.models import SpanHandle, SpanRecord, SpanStatus
from harnesslab.telemetry.memory_span_recorder import MemorySpanRecorder


class LocalSpanRecorder(MemorySpanRecorder):
    """Write one JSON line per completed span to local JSONL."""

    def __init__(
        self,
        file_path: Path,
        *,
        clock: ClockPort | None = None,
        resource: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(clock=clock, resource=resource)
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def file_path(self) -> Path:
        return self._file_path

    def end_span(
        self,
        handle: SpanHandle,
        *,
        status: SpanStatus = "ok",
        status_message: str | None = None,
        attributes: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> SpanRecord:
        record = super().end_span(
            handle,
            status=status,
            status_message=status_message,
            attributes=attributes,
            metrics=metrics,
        )
        line = json.dumps(record.model_dump(mode="json"), ensure_ascii=True)
        with self._file_path.open("a", encoding="utf-8") as handle_file:
            handle_file.write(line + "\n")
        return record
