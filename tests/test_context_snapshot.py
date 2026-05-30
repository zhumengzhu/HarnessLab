"""Phase 2.6 commit 1: ContextSnapshot + model_call payload tests."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.cli import build_runtime
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.context import (
    ContextSnapshot,
    make_conversation_snapshot,
    merge_adapter_breakdown,
)
from harnesslab.core.models import Decision, Message, Session


def _msg(role: str, content: str) -> Message:
    return Message(
        id=f"m_{role[:1]}_{abs(hash(content)) % 10000}",
        session_id="s_test",
        role=role,  # type: ignore[arg-type]
        content=content,
        created_at=datetime.now(UTC),
    )


# ---------- make_conversation_snapshot ----------


def test_snapshot_empty_messages_returns_zero_conversation_tokens() -> None:
    snap = make_conversation_snapshot([], RuntimeLimits())
    assert snap.conversation_tokens == 0
    assert snap.message_count == 0
    assert snap.usage_ratio == 0.0
    assert snap.threshold_ratio == 0.0


def test_snapshot_counts_messages_and_estimates_tokens() -> None:
    limits = RuntimeLimits(
        context_window_tokens=1000,
        compaction_threshold_tokens=500,
    )
    messages = [_msg("user", "x" * 400), _msg("assistant", "y" * 400)]
    snap = make_conversation_snapshot(messages, limits)
    # 800 chars / 4 = 200 tokens; both messages counted.
    assert snap.conversation_tokens == 200
    assert snap.message_count == 2
    assert snap.limit_tokens == 1000
    assert snap.compaction_threshold_tokens == 500
    assert snap.usage_ratio == 0.2
    assert snap.threshold_ratio == 0.4
    assert snap.context_breakdown_tokens is not None
    assert snap.context_breakdown_tokens["conversation"] == 200
    assert snap.context_breakdown_tokens["summarized_conversation"] == 0


def test_snapshot_threshold_ratio_can_exceed_one() -> None:
    limits = RuntimeLimits(
        context_window_tokens=10_000,
        compaction_threshold_tokens=100,
    )
    snap = make_conversation_snapshot([_msg("user", "x" * 800)], limits)
    # 200 tokens / threshold 100 = 2.0 — i.e. compaction is overdue.
    assert snap.threshold_ratio == 2.0


def test_snapshot_clamps_zero_limit_to_one_so_ratios_are_finite() -> None:
    snap = make_conversation_snapshot(
        [_msg("user", "hi")],
        RuntimeLimits(context_window_tokens=0, compaction_threshold_tokens=0),
    )
    assert snap.limit_tokens >= 1
    assert snap.compaction_threshold_tokens >= 1
    assert snap.usage_ratio >= 0.0


def test_snapshot_tracks_compaction_summary_tokens_separately() -> None:
    summary = (
        "<system-reminder>\n"
        "[Compacted earlier conversation: 3 messages]\n"
        "- item\n"
        "</system-reminder>"
    )
    snap = make_conversation_snapshot(
        [_msg("system", summary), _msg("user", "hello")],
        RuntimeLimits(),
    )
    assert snap.context_breakdown_tokens is not None
    assert snap.context_breakdown_tokens["summarized_conversation"] > 0
    assert snap.context_breakdown_tokens["conversation"] > 0


# ---------- merge_adapter_breakdown ----------


def test_merge_adapter_meta_fills_prompt_fields() -> None:
    base = make_conversation_snapshot([], RuntimeLimits())
    merged = merge_adapter_breakdown(
        base,
        {
            "prompt_tokens_estimate": 320,
            "static_block_tokens": 200,
            "dynamic_block_tokens": 80,
            "prompt_block_names": ["identity", "harness", "env"],
            "prompt_block_breakdown": {
                "system_prompt": 210,
                "rules": 90,
                "tool_definitions": 20,
                "skills": 0,
                "subagent_definitions": 0,
            },
        },
    )
    assert merged.prompt_tokens_estimate == 320
    assert merged.static_block_tokens == 200
    assert merged.dynamic_block_tokens == 80
    assert merged.prompt_block_names == ["identity", "harness", "env"]
    assert merged.context_breakdown_tokens is not None
    assert merged.context_breakdown_tokens["system_prompt"] == 210
    assert merged.context_breakdown_tokens["rules"] == 90


def test_merge_adapter_meta_ignores_non_dict() -> None:
    base = make_conversation_snapshot([], RuntimeLimits())
    assert merge_adapter_breakdown(base, None) == base
    assert merge_adapter_breakdown(base, "garbage") == base  # type: ignore[arg-type]


def test_merge_adapter_meta_clamps_negative_values_to_none() -> None:
    base = make_conversation_snapshot([], RuntimeLimits())
    merged = merge_adapter_breakdown(
        base,
        {"prompt_tokens_estimate": -3, "static_block_tokens": "bad"},
    )
    assert merged.prompt_tokens_estimate is None
    assert merged.static_block_tokens is None


def test_build_prompt_block_meta_categories_static_blocks() -> None:
    from harnesslab.core.context import build_prompt_block_meta, category_for_prompt_block
    from harnesslab.core.prompt.composer import DEFAULT_STATIC_BLOCKS

    assert category_for_prompt_block("identity", "system") == "system_prompt"
    assert category_for_prompt_block("safety", "system") == "rules"
    assert category_for_prompt_block("tool_guide", "system") == "tool_definitions"

    meta = build_prompt_block_meta(DEFAULT_STATIC_BLOCKS)
    breakdown = meta["prompt_block_breakdown"]
    assert breakdown["system_prompt"] > 0
    assert breakdown["rules"] > 0


def test_build_prompt_block_meta_includes_wire_tool_specs() -> None:
    from harnesslab.core.context import build_prompt_block_meta
    from harnesslab.core.prompt.block import PromptBlock

    blocks = [
        PromptBlock(
            name="identity",
            content="You are a test agent.",
            origin="static:00_identity.md",
        ),
    ]
    wire = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "read a file",
                "parameters": {"type": "object"},
            },
        }
    ]
    meta = build_prompt_block_meta(blocks, wire_tool_specs=wire)
    breakdown = meta["prompt_block_breakdown"]
    assert breakdown["system_prompt"] > 0
    assert breakdown["tool_definitions"] > 0


# ---------- loop integration: model_call event carries snapshot ----------


def test_model_call_event_includes_context_snapshot(tmp_path) -> None:
    import json

    loop = build_runtime(tmp_path)
    session = loop.start(goal="snapshot smoke")
    loop.run_turn(session.id, "hello")

    spans_path = tmp_path / ".harnesslab" / "spans.jsonl"
    assert spans_path.exists()
    spans = [
        json.loads(line)
        for line in spans_path.read_text(encoding="utf-8").splitlines()
    ]
    llm_spans = [s for s in spans if s["name"] == "llm.generate"]
    assert llm_spans, "expected at least one llm.generate span"

    ctx = llm_spans[0]["metrics"]["context"]
    snap = ContextSnapshot.model_validate(ctx)
    assert "prompt_tokens_estimate" not in ctx
    assert snap.conversation_tokens > 0
    assert snap.message_count >= 1
    assert snap.limit_tokens >= 1


def test_model_call_event_includes_adapter_prompt_breakdown(tmp_path) -> None:
    """When the adapter advertises prompt-side fields, the loop folds them in."""

    from harnesslab.core.contracts import ModelPort
    from harnesslab.core.loop import HarnessLoop
    from harnesslab.policy.default_policy import DefaultPolicy
    from harnesslab.session.in_memory import InMemorySessionStore
    from harnesslab.telemetry.local_span_recorder import LocalSpanRecorder
    from harnesslab.tools.registry import ToolRegistry

    class ChattyModel(ModelPort):
        def decide(self, session: Session, user_input: str) -> Decision:
            return Decision(kind="final", assistant_message="ok")

        def last_call_meta(self) -> dict[str, object]:
            return {
                "model_name": "chatty",
                "provider": "test",
                "prompt_tokens_estimate": 1234,
                "static_block_tokens": 500,
                "dynamic_block_tokens": 200,
                "prompt_block_names": ["identity", "env"],
                "prompt_block_breakdown": {
                    "system_prompt": 350,
                    "rules": 50,
                    "tool_definitions": 30,
                    "skills": 40,
                    "subagent_definitions": 0,
                },
            }

    trace_path = tmp_path / "spans.jsonl"
    loop = HarnessLoop(
        model=ChattyModel(),
        policy=DefaultPolicy(workspace_root=tmp_path),
        tools=ToolRegistry(),
        sessions=InMemorySessionStore(),
        spans=LocalSpanRecorder(trace_path),
    )
    session = loop.start(goal="adapter breakdown")
    loop.run_turn(session.id, "hi")

    import json

    spans = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    llm_spans = [s for s in spans if s["name"] == "llm.generate"]
    assert llm_spans
    ctx = llm_spans[0]["metrics"]["context"]
    assert ctx["prompt_tokens_estimate"] == 1234
    assert ctx["static_block_tokens"] == 500
    assert ctx["dynamic_block_tokens"] == 200
    assert ctx["prompt_block_names"] == ["identity", "env"]
    assert ctx["context_breakdown_tokens"]["system_prompt"] == 350
    assert ctx["context_breakdown_tokens"]["skills"] == 40
