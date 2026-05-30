"""model_call trace payload includes provider failover metadata."""

from __future__ import annotations

import json
from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, Session
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.providers.failover import FailoverModel
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.local_span_recorder import LocalSpanRecorder
from harnesslab.tools.registry import ToolRegistry


class _FailingModel:
    def decide(self, session: Session, user_input: str) -> Decision:
        return Decision(
            kind="final",
            assistant_message="DeepSeek request failed: APIStatusError: 503",
        )

    def last_call_meta(self) -> dict[str, str]:
        return {"provider": "deepseek"}


def _read_spans(workspace_root: Path) -> list[dict]:
    spans_path = workspace_root / "spans.jsonl"
    return [json.loads(line) for line in spans_path.read_text().splitlines() if line]


def test_model_call_trace_includes_failover_metadata(tmp_path: Path) -> None:
    model = FailoverModel(
        [_FailingModel(), SimpleModel()],
        backend_labels=["deepseek", "simple"],
    )
    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(tmp_path),
        sessions=InMemorySessionStore(),
        tools=ToolRegistry(),
        spans=LocalSpanRecorder(tmp_path / "spans.jsonl"),
        clock=SystemClock(),
        ids=UuidIdProvider(),
        workspace_root=tmp_path,
    )
    session = loop.start(goal="failover trace")
    loop.run_turn(session.id, "hello")

    llm_spans = [s for s in _read_spans(tmp_path) if s["name"] == "llm.generate"]
    assert len(llm_spans) == 1
    span = llm_spans[0]
    assert span["attributes"]["harnesslab.failover.attempts"] == 2
    assert span["attributes"]["harnesslab.decision.kind"] == "final"
