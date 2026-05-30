"""Tests for mid-turn steer injection."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from harnesslab.cli import build_runtime
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision
from harnesslab.core.turn_steer import TurnSteerBuffer
from harnesslab.replay.trace_reader import read_trace
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder


class _TwoStepToolModel:
    def __init__(self) -> None:
        self.calls = 0
        self._gate = threading.Event()

    def decide(self, session, user_input: str) -> Decision:  # noqa: ANN001
        self.calls += 1
        if self.calls == 1:
            self._gate.wait(timeout=2.0)
            return Decision(
                kind="tool",
                tool_name="read_file",
                tool_args={"path": "notes/a.txt"},
            )
        return Decision(kind="final", assistant_message="done after steer")

    def release(self) -> None:
        self._gate.set()


def _build_loop(tmp_path: Path, model: _TwoStepToolModel, steer: TurnSteerBuffer) -> HarnessLoop:
    loop = build_runtime(
        tmp_path,
        storage_backend="memory",
        trace=JsonlTraceRecorder(tmp_path / "trace.jsonl"),
    )
    loop._model = model  # noqa: SLF001
    loop._turn_steer = steer
    return loop


def test_steer_injects_user_message_before_next_step(tmp_path: Path) -> None:
    target = tmp_path / "notes" / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hello", encoding="utf-8")

    steer = TurnSteerBuffer()
    model = _TwoStepToolModel()
    loop = _build_loop(tmp_path, model, steer)

    session = loop.start(goal="steer me")
    errors: list[BaseException] = []

    def run_turn() -> None:
        try:
            loop.run_session(session.id, "go", max_steps=4)
        except BaseException as exc:  # pragma: no cover - surfaced via errors
            errors.append(exc)

    worker = threading.Thread(target=run_turn)
    worker.start()
    time.sleep(0.05)
    steer.push(session.id, "also summarize notes/a.txt")
    model.release()
    worker.join(timeout=5.0)

    assert not errors
    loaded = loop._sessions.get(session.id)  # noqa: SLF001
    user_texts = [m.content for m in loaded.messages if m.role == "user"]
    assert "also summarize notes/a.txt" in user_texts

    events = read_trace(tmp_path / "trace.jsonl")
    steer_events = [e for e in events if e.event_type == "user_steer_received"]
    assert len(steer_events) == 1
    assert steer_events[0].payload["user_input"] == "also summarize notes/a.txt"
