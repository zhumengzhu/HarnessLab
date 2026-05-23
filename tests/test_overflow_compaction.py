"""Phase 2.4 commit 2: overflow recovery + live summarizer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from harnesslab.core.compaction import (
    LiveSummarizer,
    ModelOverflowError,
    _fallback_summarizer,
)
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, Message, Session
from harnesslab.core.replay import ReplayTraceRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.providers.deepseek import DeepSeekModel
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.file_tools import WriteFileTool
from harnesslab.tools.registry import ToolRegistry

# ---------- ModelOverflowError plumbing ----------


def test_model_overflow_error_carries_estimated_tokens() -> None:
    err = ModelOverflowError("nope", estimated_tokens=12345)
    assert str(err) == "nope"
    assert err.estimated_tokens == 12345


# ---------- loop catches overflow, emergency-compacts, retries ----------


class _OverflowOnceThenAnswerModel:
    """First call raises ModelOverflowError; second call returns the
    decision passed in at construction time."""

    def __init__(self, recovery: Decision) -> None:
        self._recovery = recovery
        self.calls = 0
        self._snapshots: list[list[str]] = []

    def decide(self, session: Session, user_input: str) -> Decision:
        self.calls += 1
        self._snapshots.append([m.content[:24] for m in session.messages])
        if self.calls == 1:
            raise ModelOverflowError(
                "simulated context overflow", estimated_tokens=999_999
            )
        return self._recovery

    @property
    def snapshots(self) -> list[list[str]]:
        return self._snapshots


def _build_loop(
    tmp_path: Path,
    model,
    *,
    threshold: int = 10_000,
    keep_last: int = 4,
) -> tuple[HarnessLoop, ReplayTraceRecorder]:
    limits = RuntimeLimits(
        compaction_threshold_tokens=threshold,
        compaction_keep_last_messages=keep_last,
    )
    tools = ToolRegistry()
    tools.register(WriteFileTool(tmp_path, limits=limits))
    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
        limits=limits,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
    )
    return loop, recorder


def test_overflow_triggers_emergency_compaction_and_retry(tmp_path: Path) -> None:
    model = _OverflowOnceThenAnswerModel(
        recovery=Decision(kind="final", assistant_message="recovered"),
    )
    loop, recorder = _build_loop(tmp_path, model, keep_last=4)
    session = loop.start(goal="overflow path")
    for i in range(8):
        session.messages.append(
            Message(
                id=f"msg_seed_{i}",
                role="user" if i % 2 == 0 else "assistant",
                content=f"seed-{i}-{'x' * 50}",
                session_id=session.id,
            )
        )

    response = loop.run_session(session.id, "trigger", max_steps=2)

    assert response == "recovered"
    # Two model decisions: one overflow + one recovery.
    assert model.calls == 2

    starts = [e for e in recorder.events if e.event_type == "compaction_started"]
    completes = [e for e in recorder.events if e.event_type == "compaction_completed"]
    # The threshold is generous, so the only compaction event must be
    # the overflow-triggered emergency one.
    assert len(starts) == 1
    assert starts[0].payload["trigger"] == "overflow"
    assert starts[0].payload["keep_last"] == 2  # max(1, 4 // 2)
    assert starts[0].payload["estimated_tokens"] == 999_999
    assert len(completes) == 1
    assert completes[0].payload["trigger"] == "overflow"
    assert completes[0].payload["removed_messages"] > 0

    # The retry must see the compacted message list (system summary +
    # the surviving recent messages + the new user turn).
    assert model.snapshots[1][0].startswith("<system-reminder>") or model.snapshots[1][
        0
    ].startswith("[Compacted")


class _AlwaysOverflowModel:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, session: Session, user_input: str) -> Decision:
        self.calls += 1
        raise ModelOverflowError("still too long", estimated_tokens=1)


def test_second_overflow_terminates_with_explanatory_final(tmp_path: Path) -> None:
    model = _AlwaysOverflowModel()
    loop, recorder = _build_loop(tmp_path, model)
    session = loop.start(goal="permanent overflow")
    session.messages.append(
        Message(id="msg_seed", role="user", content="x" * 100, session_id=session.id)
    )

    response = loop.run_session(session.id, "go", max_steps=1)
    assert "Context window exceeded" in response
    assert model.calls == 2  # original + one retry

    finished = [e for e in recorder.events if e.event_type == "session_finished"]
    assert finished[0].payload["reason"] == "final"
    decisions = [e for e in recorder.events if e.event_type == "decision_made"]
    assert decisions[-1].payload["kind"] == "final"


# ---------- DeepSeek maps API overflow → ModelOverflowError ----------


def _ovf_session() -> Session:
    s = Session(
        id="ses_test",
        goal="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    s.messages.append(
        Message(
            id="msg_u",
            role="user",
            content="hi",
            session_id="ses_test",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    return s


def test_deepseek_raises_overflow_on_context_length_exceeded() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "context_length_exceeded",
                    "message": "Your request exceeded the model's context length",
                }
            },
        )

    import pytest

    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelOverflowError) as excinfo:
        model.decide(_ovf_session(), "hi")
    assert "context length" in str(excinfo.value).lower()


def test_deepseek_other_400_still_returns_final_decision() -> None:
    """A garden-variety 400 (bad request, NOT overflow) must
    continue to surface as a `final` decision so the loop's overflow
    path is reserved for real overflow situations."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"code": "invalid_request_error", "message": "bad arg"}}
        )

    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=httpx.MockTransport(handler),
    )
    decision = model.decide(_ovf_session(), "hi")
    assert decision.kind == "final"
    assert "DeepSeek request failed" in (decision.assistant_message or "")


# ---------- LiveSummarizer ----------


class _StubModel:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[str] = []

    def decide(self, session: Session, user_input: str) -> Decision:
        # Capture the last user message so the test can assert the
        # transcript was actually passed in.
        self.calls.append(session.messages[-1].content)
        return Decision(kind="final", assistant_message=self._reply)


def test_live_summarizer_fences_model_output_in_system_reminder() -> None:
    model = _StubModel(reply="- talked about widgets\n- agreed to refactor")
    summ = LiveSummarizer(model)
    older = [
        Message(id="m1", role="user", content="hello", session_id="ses"),
        Message(id="m2", role="assistant", content="hi back", session_id="ses"),
    ]
    body = summ(older)
    assert body.startswith("<system-reminder>")
    assert body.endswith("</system-reminder>")
    assert "Compacted earlier conversation: 2 messages" in body
    assert "widgets" in body
    # The full transcript must have been passed as the user message.
    assert "[user] hello" in model.calls[0]
    assert "[assistant] hi back" in model.calls[0]


def test_live_summarizer_falls_back_when_model_returns_empty() -> None:
    model = _StubModel(reply="")
    summ = LiveSummarizer(model)
    older = [Message(id="m1", role="user", content="topic A", session_id="ses")]
    body = summ(older)
    assert body == _fallback_summarizer(older)


# ---------- trace surface ----------


def test_overflow_compaction_appears_in_jsonl_trace(tmp_path: Path) -> None:
    from harnesslab.cli import build_runtime

    class _OverflowOnce:
        def __init__(self) -> None:
            self.calls = 0

        def decide(self, session: Session, user_input: str) -> Decision:
            self.calls += 1
            if self.calls == 1:
                raise ModelOverflowError("ctx full", estimated_tokens=200_000)
            return Decision(kind="final", assistant_message="recovered ok")

    loop = build_runtime(
        tmp_path,
        limits=RuntimeLimits(
            compaction_threshold_tokens=10_000_000,  # never triggers threshold path
            compaction_keep_last_messages=2,
        ),
    )
    loop._model = _OverflowOnce()  # type: ignore[attr-defined]
    session = loop.start(goal="trace overflow")
    session.messages.append(
        Message(id="msg_seed", role="user", content="x" * 300, session_id=session.id)
    )

    loop.run_session(session.id, "go", max_steps=2)

    trace_path = tmp_path / ".harnesslab" / "trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text().splitlines() if line]
    overflow_events = [
        e for e in events
        if e["event_type"] == "compaction_started"
        and e["payload"].get("trigger") == "overflow"
    ]
    assert len(overflow_events) == 1
    assert overflow_events[0]["payload"]["estimated_tokens"] == 200_000
