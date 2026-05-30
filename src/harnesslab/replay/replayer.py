"""Deterministic single-session replay of a span JSONL trace (Observability v2).

The replayer reconstructs ``(user_input, [decisions...])`` per turn from
completed spans, builds a ``ReplayModel`` over the flattened decision list,
and re-drives the production loop with ``FrozenClock`` + ``SeqIdProvider``.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, SpanRecord, ToolCall, ToolResult
from harnesslab.core.replay import ReplayModel, ReplaySpanRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.eval.runner import _build_tool_registry
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.replay.span_reader import group_by_session
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.span_attributes import (
    HARNESSLAB_COMPACTION_KEEP_LAST,
    HARNESSLAB_COMPACTION_THRESHOLD_TOKENS,
    HARNESSLAB_COMPACTION_TRIGGER,
    HARNESSLAB_MAX_STEPS,
    HARNESSLAB_PARENT_SESSION_ID,
    HARNESSLAB_SESSION_GOAL,
    HARNESSLAB_SESSION_ID,
    HARNESSLAB_USER_INPUT_PREVIEW,
    SPAN_CONTEXT_COMPACT,
    SPAN_LLM_GENERATE,
    SPAN_SUB_AGENT_RUN,
    SPAN_TURN,
)


class ReplaySpawnSubAgentTool:
    """Replay stub: return recorded spawn output without nesting a live child."""

    name = "spawn_sub_agent"
    description = "Replay stub for spawn_sub_agent"
    args_schema: dict = {
        "type": "object",
        "properties": {"goal": {"type": "string"}},
        "required": ["goal"],
    }

    def __init__(self, output: str) -> None:
        self._output = output

    def execute(self, _call: ToolCall) -> ToolResult:
        return ToolResult(ok=True, output=self._output)


class UnreplayableTraceError(Exception):
    """Raised when spans lack the structure required to replay them."""


TurnPlan = tuple[str, list[Decision]]


def replay_session(
    spans: list[SpanRecord],
    workspace_root: Path | None = None,
) -> list[SpanRecord]:
    """Replay one single-session span sequence; return the new spans."""

    if not spans:
        raise UnreplayableTraceError("span trace is empty")

    segments = _session_segments(spans)
    replayed = _drive_loop(segments, workspace_root, spans)
    return _align_replayed_sessions(segments, replayed)


def _session_segments(spans: list[SpanRecord]) -> list[list[SpanRecord]]:
    grouped = group_by_session(spans)
    return list(grouped.values())


def _extract_turns(spans: list[SpanRecord]) -> list[TurnPlan]:
    turns: list[TurnPlan] = []
    for bucket in _turn_buckets(spans):
        turn_span = _turn_root(bucket)
        if turn_span is None:
            continue
        user_input = _user_input_from_turn(turn_span)
        if user_input is None:
            raise UnreplayableTraceError(
                f"turn trace {turn_span.trace_id!r} missing user input"
            )
        decisions = _decisions_from_turn(bucket)
        terminal = turn_span.attributes.get("harnesslab.terminal.reason")
        if not decisions and terminal not in {
            "remember",
            "remember_global",
            "compact",
        }:
            if turn_span.attributes.get("harnesslab.steps.used", 0) == 0:
                turns.append((user_input, []))
                continue
            raise UnreplayableTraceError(
                f"turn {turn_span.turn_index} missing decisions"
            )
        turns.append((user_input, decisions))
    return turns


def _turn_buckets(spans: list[SpanRecord]) -> list[list[SpanRecord]]:
    buckets: dict[str, list[SpanRecord]] = {}
    turn_index: dict[str, int] = {}
    for span in spans:
        buckets.setdefault(span.trace_id, []).append(span)
        turn_index[span.trace_id] = span.turn_index
    ordered = sorted(buckets.keys(), key=lambda tid: turn_index[tid])
    return [buckets[tid] for tid in ordered]


def _turn_root(bucket: list[SpanRecord]) -> SpanRecord | None:
    for span in bucket:
        if span.name == SPAN_TURN and span.parent_span_id is None:
            return span
    return None


def _user_input_from_turn(turn_span: SpanRecord) -> str | None:
    for event in turn_span.events:
        if event.name == "user.input.received":
            raw = event.attributes.get("user_input")
            if isinstance(raw, str):
                return raw
    preview = turn_span.attributes.get(HARNESSLAB_USER_INPUT_PREVIEW)
    if isinstance(preview, str) and preview:
        return preview
    return None


def _decisions_from_turn(bucket: list[SpanRecord]) -> list[Decision]:
    decisions: list[Decision] = []
    for span in bucket:
        if span.name != SPAN_LLM_GENERATE:
            continue
        decision = _decision_from_llm_span(span, bucket)
        if decision is not None:
            decisions.append(decision)
    return decisions


def _decision_from_llm_span(
    llm_span: SpanRecord,
    bucket: list[SpanRecord],
) -> Decision | None:
    for step in bucket:
        if step.span_id != llm_span.parent_span_id:
            continue
        for event in step.events:
            if event.name != "decision.applied":
                continue
            return _decision_from_payload(event.attributes, index=llm_span.turn_index)
    attrs = dict(llm_span.attributes)
    kind = attrs.get("harnesslab.decision.kind")
    if not isinstance(kind, str):
        return None
    return Decision(
        kind=kind,  # type: ignore[arg-type]
        tool_name=attrs.get("tool_name") if isinstance(attrs.get("tool_name"), str) else None,
        tool_args=attrs.get("tool_args") if isinstance(attrs.get("tool_args"), dict) else {},
        assistant_message=(
            attrs.get("assistant_message")
            if isinstance(attrs.get("assistant_message"), str)
            else None
        ),
    )


def _decision_from_payload(payload: dict, index: int) -> Decision:
    if "kind" not in payload:
        raise UnreplayableTraceError(f"decision at turn {index} missing kind")
    try:
        return Decision(
            kind=payload["kind"],
            tool_name=payload.get("tool_name"),
            tool_args=payload.get("tool_args") or {},
            assistant_message=payload.get("assistant_message"),
        )
    except Exception as exc:
        raise UnreplayableTraceError(
            f"decision at turn {index} invalid: {exc}"
        ) from exc


def _segment_goal_and_parent(segment: list[SpanRecord]) -> tuple[str, str | None]:
    for span in segment:
        if span.name != SPAN_TURN:
            continue
        goal = span.attributes.get(HARNESSLAB_SESSION_GOAL)
        if isinstance(goal, str):
            parent_id = span.attributes.get(HARNESSLAB_PARENT_SESSION_ID)
            parent = str(parent_id) if isinstance(parent_id, str) and parent_id else None
            return goal, parent
    return "", None


def _segment_has_spawn_stub(segment: list[SpanRecord]) -> bool:
    return any(span.name == SPAN_SUB_AGENT_RUN for span in segment)


def _spawn_tool_output_from_segment(segment: list[SpanRecord]) -> str:
    for span in segment:
        if span.name != "tool.spawn_sub_agent":
            continue
        preview = span.metrics.get("output_preview")
        if isinstance(preview, str) and preview.strip():
            return preview
        child_id = span.attributes.get("harnesslab.child_session.id")
        if isinstance(child_id, str):
            return json.dumps({"child_session_id": child_id}, ensure_ascii=False)
    for span in segment:
        if span.name != SPAN_SUB_AGENT_RUN:
            continue
        child_id = span.attributes.get("harnesslab.child_session.id")
        if isinstance(child_id, str):
            return json.dumps({"child_session_id": child_id}, ensure_ascii=False)
    return "{}"


def _align_replayed_sessions(
    segments: list[list[SpanRecord]],
    replayed: list[SpanRecord],
) -> list[SpanRecord]:
    grouped = group_by_session(replayed)
    replay_sids = list(grouped.keys())
    aligned: list[SpanRecord] = []
    for idx, segment in enumerate(segments):
        if idx >= len(replay_sids) or not segment:
            continue
        original_sid = segment[0].session_id
        replay_sid = replay_sids[idx]
        for span in grouped[replay_sid]:
            attrs = dict(span.attributes)
            if attrs.get(HARNESSLAB_SESSION_ID) == replay_sid:
                attrs[HARNESSLAB_SESSION_ID] = original_sid
            aligned.append(
                span.model_copy(update={"session_id": original_sid, "attributes": attrs})
            )
    return aligned


def _limits_from_spans(spans: list[SpanRecord]) -> RuntimeLimits:
    base = RuntimeLimits()
    for span in spans:
        if span.name != SPAN_CONTEXT_COMPACT:
            continue
        trigger = span.attributes.get(HARNESSLAB_COMPACTION_TRIGGER)
        keep_last = span.attributes.get(HARNESSLAB_COMPACTION_KEEP_LAST)
        threshold = span.attributes.get(HARNESSLAB_COMPACTION_THRESHOLD_TOKENS)
        overrides: dict[str, int] = {}
        if isinstance(threshold, int):
            overrides["compaction_threshold_tokens"] = threshold
        elif trigger == "threshold":
            overrides["compaction_threshold_tokens"] = 40
        if isinstance(keep_last, int):
            overrides["compaction_keep_last_messages"] = keep_last
        if overrides:
            return replace(base, **overrides)
    return base


def _drive_loop(
    segments: list[list[SpanRecord]],
    workspace_root: Path | None,
    source_spans: list[SpanRecord],
) -> list[SpanRecord]:
    if workspace_root is None:
        with tempfile.TemporaryDirectory() as ws:
            return _run(Path(ws), segments, source_spans)
    return _run(workspace_root, segments, source_spans)


def _shell_profile_from_segments(segments: list[list[SpanRecord]]) -> str | None:
    for segment in segments:
        for span in segment:
            if span.name != SPAN_TURN:
                continue
            profile = span.attributes.get("harnesslab.shell_profile")
            if profile:
                return str(profile)
    return None


def _run(
    workspace: Path,
    segments: list[list[SpanRecord]],
    source_spans: list[SpanRecord],
) -> list[SpanRecord]:
    limits = _limits_from_spans(source_spans)
    tools = _build_tool_registry(workspace, limits)
    shell_profile = _shell_profile_from_segments(segments)
    enable_spawn = any(_segment_has_spawn_stub(segment) for segment in segments)

    session_plans: list[tuple[list[SpanRecord], str, str | None, list[TurnPlan]]] = []
    for segment in segments:
        goal, parent_id = _segment_goal_and_parent(segment)
        session_plans.append((segment, goal, parent_id, _extract_turns(segment)))

    recorder = ReplaySpanRecorder()
    loop = HarnessLoop(
        model=ReplayModel(decisions=[]),
        policy=DefaultPolicy(
            workspace_root=workspace,
            shell_profile=shell_profile,
            enable_spawn_sub_agent=enable_spawn,
        ),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        limits=limits,
        memory=InMemoryMemoryStore(),
        workspace_root=workspace,
    )

    for segment, goal, parent_id, turns in session_plans:
        segment_decisions = [d for _, ds in turns for d in ds]
        loop._model = ReplayModel(decisions=segment_decisions)  # noqa: SLF001
        if _segment_has_spawn_stub(segment):
            tools.register(
                ReplaySpawnSubAgentTool(_spawn_tool_output_from_segment(segment))
            )
        if parent_id:
            session = loop.start_child(goal=goal, parent_session_id=parent_id)
        else:
            session = loop.start(goal=goal)
        turn_buckets = _turn_buckets(segment)
        for (user_input, decisions), bucket in zip(turns, turn_buckets, strict=True):
            turn_span = _turn_root(bucket)
            max_steps = max(1, len(decisions))
            if turn_span is not None:
                recorded = turn_span.attributes.get(HARNESSLAB_MAX_STEPS)
                if isinstance(recorded, int):
                    max_steps = max(max_steps, recorded)
            loop.run_session(session.id, user_input, max_steps=max_steps)
    return recorder.spans
