"""Phase 2.4 commit 1: compaction infrastructure + loop integration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from harnesslab.core.compaction import (
    compact_messages,
    estimate_messages_tokens,
    estimate_tokens,
    should_compact,
)
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, Message
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry


def _msg(content: str, role: str = "user", session_id: str = "ses_x") -> Message:
    return Message(
        id=f"msg_{role}_{content[:6]}",
        role=role,  # type: ignore[arg-type]
        content=content,
        created_at=datetime(2026, 5, 23, tzinfo=UTC),
        session_id=session_id,
    )


# ---------- estimator ----------


def test_estimate_tokens_empty_text_costs_one_token() -> None:
    assert estimate_tokens("") == 1


def test_estimate_tokens_approximates_len_over_four() -> None:
    assert estimate_tokens("hello world") == max(1, len("hello world") // 4)
    assert estimate_tokens("x" * 400) == 100


def test_estimate_messages_tokens_sums_message_content() -> None:
    msgs = [_msg("aaaaaaaa"), _msg("bbbb")]
    assert estimate_messages_tokens(msgs) == estimate_tokens("aaaaaaaa") + estimate_tokens(
        "bbbb"
    )


# ---------- should_compact ----------


def test_should_compact_false_when_empty() -> None:
    assert should_compact([], threshold_tokens=10) is False


def test_should_compact_false_below_threshold() -> None:
    msgs = [_msg("x" * 20)]  # ~5 tokens
    assert should_compact(msgs, threshold_tokens=100) is False


def test_should_compact_true_above_threshold() -> None:
    msgs = [_msg("x" * 1000), _msg("y" * 1000)]  # ~500 tokens
    assert should_compact(msgs, threshold_tokens=100) is True


# ---------- compact_messages ----------


def test_compact_returns_messages_unchanged_when_short() -> None:
    msgs = [_msg("a"), _msg("b")]
    result, stats = compact_messages(msgs, keep_last=4)
    assert result == msgs
    assert stats == {"kept_messages": 2, "removed_messages": 0, "summary_chars": 0}


def test_compact_keeps_last_n_and_summarizes_the_rest() -> None:
    msgs = [
        _msg("opening", role="user"),
        _msg("middle 1", role="assistant"),
        _msg("middle 2", role="user"),
        _msg("recent 1", role="assistant"),
        _msg("recent 2", role="user"),
    ]
    result, stats = compact_messages(msgs, keep_last=2)
    assert len(result) == 3
    assert result[0].role == "system"
    assert "Compacted earlier conversation" in result[0].content
    assert "3 messages" in result[0].content
    assert [m.content for m in result[1:]] == ["recent 1", "recent 2"]
    assert stats["kept_messages"] == 2
    assert stats["removed_messages"] == 3
    assert stats["summary_chars"] == len(result[0].content)


def test_compact_with_keep_last_zero_replaces_everything() -> None:
    msgs = [_msg("first"), _msg("second")]
    result, _ = compact_messages(msgs, keep_last=0)
    assert len(result) == 1
    assert result[0].role == "system"


def test_compact_uses_custom_summarizer_when_supplied() -> None:
    msgs = [_msg("a"), _msg("b"), _msg("c"), _msg("d")]
    result, stats = compact_messages(
        msgs,
        keep_last=1,
        summarizer=lambda older: f"CUSTOM_SUMMARY({len(older)})",
    )
    assert result[0].content == "CUSTOM_SUMMARY(3)"
    assert stats["summary_chars"] == len("CUSTOM_SUMMARY(3)")


def test_compact_summary_message_uses_supplied_clock_and_id() -> None:
    msgs = [_msg("a"), _msg("b"), _msg("c"), _msg("d")]
    fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
    result, _ = compact_messages(
        msgs,
        keep_last=1,
        now=fixed_now,
        new_id=lambda prefix: f"{prefix}_xyz",
    )
    assert result[0].id == "msg_xyz"
    assert result[0].created_at == fixed_now


# ---------- loop integration ----------


def _build_loop_with_low_threshold(
    tmp_path: Path,
    decisions: list[Decision],
    *,
    threshold: int,
    keep_last: int,
) -> tuple[HarnessLoop, ReplayTraceRecorder]:
    limits = RuntimeLimits(
        compaction_threshold_tokens=threshold,
        compaction_keep_last_messages=keep_last,
    )
    tools = ToolRegistry()
    tools.register(ReadFileTool(tmp_path, limits=limits))
    tools.register(WriteFileTool(tmp_path, limits=limits))
    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel(decisions=decisions),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
        limits=limits,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
    )
    return loop, recorder


def test_loop_emits_compaction_events_when_threshold_exceeded(tmp_path: Path) -> None:
    """Two pre-seeded long messages should push the next step past
    the threshold, triggering a single compaction event pair."""
    decisions = [Decision(kind="final", assistant_message="done")]
    loop, recorder = _build_loop_with_low_threshold(
        tmp_path, decisions, threshold=20, keep_last=2
    )
    session = loop.start(goal="compact me")
    session.messages.append(
        Message(id="msg_seed_a", role="user", content="x" * 400, session_id=session.id)
    )
    session.messages.append(
        Message(id="msg_seed_b", role="assistant", content="y" * 400, session_id=session.id)
    )

    loop.run_session(session.id, "next turn", max_steps=2)

    starts = [e for e in recorder.events if e.event_type == "compaction_started"]
    completes = [e for e in recorder.events if e.event_type == "compaction_completed"]
    assert len(starts) == 1
    assert len(completes) == 1
    assert starts[0].payload["trigger"] == "threshold"
    assert starts[0].payload["estimated_tokens"] >= 200
    assert starts[0].payload["threshold_tokens"] == 20
    assert completes[0].payload["removed_messages"] >= 1
    assert completes[0].payload["kept_messages"] == 2
    assert completes[0].payload["estimated_tokens_after"] < starts[0].payload["estimated_tokens"]


def test_loop_does_not_compact_short_sessions(tmp_path: Path) -> None:
    decisions = [Decision(kind="final", assistant_message="done")]
    loop, recorder = _build_loop_with_low_threshold(
        tmp_path, decisions, threshold=10_000, keep_last=2
    )
    session = loop.start(goal="stay short")
    loop.run_session(session.id, "hello", max_steps=1)

    assert not any(e.event_type == "compaction_started" for e in recorder.events)
    assert not any(e.event_type == "compaction_completed" for e in recorder.events)


def test_compaction_event_appears_before_model_call(tmp_path: Path) -> None:
    """Compaction must happen *before* the model is called for that
    step so the model sees the trimmed context."""
    decisions = [Decision(kind="final", assistant_message="done")]
    loop, recorder = _build_loop_with_low_threshold(
        tmp_path, decisions, threshold=20, keep_last=1
    )
    session = loop.start(goal="ordering")
    session.messages.append(
        Message(id="msg_a", role="user", content="x" * 400, session_id=session.id)
    )

    loop.run_session(session.id, "trigger", max_steps=1)

    types = [e.event_type for e in recorder.events]
    compaction_idx = types.index("compaction_started")
    model_idx = types.index("model_call")
    assert compaction_idx < model_idx


def test_compaction_replaces_session_messages_in_place(tmp_path: Path) -> None:
    decisions = [Decision(kind="final", assistant_message="done")]
    loop, _ = _build_loop_with_low_threshold(
        tmp_path, decisions, threshold=20, keep_last=2
    )
    session = loop.start(goal="state mutation")
    for i in range(6):
        session.messages.append(
            Message(
                id=f"msg_seed_{i}",
                role="user" if i % 2 == 0 else "assistant",
                content=f"seed-{i}-{'x' * 100}",
                session_id=session.id,
            )
        )
    pre_count = len(session.messages)  # 6

    loop.run_session(session.id, "trigger compaction", max_steps=1)

    refreshed = loop._sessions.get(session.id)  # type: ignore[attr-defined]
    # The system summary must be present and the message count must
    # have shrunk: 6 seeded + 1 new user input + 1 final assistant =
    # 8 without compaction, vs. 1 summary + 2 recent + 1 user + 1
    # final = 5 with compaction.
    assert any(m.role == "system" and "Compacted" in m.content for m in refreshed.messages)
    assert len(refreshed.messages) < pre_count + 2


# ---------- trace persistence ----------


def test_trace_records_compaction_events(tmp_path: Path) -> None:
    """The JSONL trace should contain the compaction event pair so
    the metrics aggregator and inspector can pick them up later."""
    from harnesslab.cli import build_runtime

    loop = build_runtime(
        tmp_path,
        limits=RuntimeLimits(
            compaction_threshold_tokens=20,
            compaction_keep_last_messages=1,
        ),
    )
    session = loop.start(goal="trace check")
    session.messages.append(
        Message(id="msg_seed", role="user", content="x" * 400, session_id=session.id)
    )
    loop.run_session(session.id, "follow up", max_steps=1)

    trace_path = tmp_path / ".harnesslab" / "trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text().splitlines() if line]
    types = [e["event_type"] for e in events]
    assert "compaction_started" in types
    assert "compaction_completed" in types
