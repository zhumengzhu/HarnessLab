from __future__ import annotations

import json
from pathlib import Path

from harnesslab.core.models import TraceEvent


class JsonlTraceRecorder:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: TraceEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=True)
        with self._file_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

