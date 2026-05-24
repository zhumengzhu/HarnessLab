"""Deterministic single-session replay of a JSONL trace.

The replayer reconstructs ``(user_input, [decisions...])`` per turn
from a trace, builds a ``ReplayModel`` over the flattened decision
list, and re-drives the production loop with ``FrozenClock`` +
``SeqIdProvider``. Each turn is replayed via
``HarnessLoop.run_session(..., max_steps=len(decisions))`` so multi-step
turns recorded by the new agentic loop round-trip correctly.
"""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, TraceEvent
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.eval.runner import _build_tool_registry
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore


class UnreplayableTraceError(Exception):
    """Raised when a trace lacks the structure required to replay it."""


# Per-turn structure produced by ``_extract_turns``: the user input that
# started the turn, plus every ``Decision`` the model produced before the
# next user input (or end of session).
TurnPlan = tuple[str, list[Decision]]


def replay_session(
    events: list[TraceEvent],
    workspace_root: Path | None = None,
) -> list[TraceEvent]:
    """Replay one single-session event sequence; return the new trace."""

    if not events:
        raise UnreplayableTraceError("trace is empty")
    if events[0].event_type != "session_started":
        raise UnreplayableTraceError(
            f"first event must be session_started, got {events[0].event_type!r}"
        )

    segments = _session_segments(events)
    return _drive_loop(segments, workspace_root, events)


def _extract_turns(events: list[TraceEvent]) -> list[TurnPlan]:
    turns: list[TurnPlan] = []
    i = 0
    while i < len(events):
        e = events[i]
        if e.event_type != "user_input_received":
            i += 1
            continue
        user_input = e.payload.get("user_input")
        if user_input is None:
            raise UnreplayableTraceError(
                f"user_input_received event #{i} missing user_input payload"
            )
        decisions, next_i = _collect_turn_decisions(events, start=i + 1)
        if not decisions:
            if not _turn_ends_without_model_call(events, i + 1, next_i):
                raise UnreplayableTraceError(
                    f"user_input_received at #{i} not followed by any decision_made"
                )
            turns.append((str(user_input), []))
            i = next_i
            continue
        turns.append((str(user_input), decisions))
        i = next_i
    return turns


def _collect_turn_decisions(
    events: list[TraceEvent],
    start: int,
) -> tuple[list[Decision], int]:
    """Collect every ``decision_made`` until the next ``user_input_received``.

    Event types other than ``decision_made`` are skipped (in particular
    ``step_started`` / ``step_completed`` / ``model_call`` / tool events
    / ``session_finished``). The function returns the decisions plus the
    index of the next event to inspect (either the next
    ``user_input_received`` or ``len(events)``).
    """

    decisions: list[Decision] = []
    j = start
    while j < len(events):
        et = events[j].event_type
        if et == "user_input_received":
            return decisions, j
        if et == "decision_made":
            decisions.append(_decision_from_payload(events[j].payload, index=j))
        j += 1
    return decisions, j


def _turn_ends_without_model_call(events: list[TraceEvent], start: int, end: int) -> bool:
    for j in range(start, end):
        e = events[j]
        reason = e.payload.get("reason") if e.event_type == "session_finished" else None
        if reason in ("remember", "remember_global"):
            return True
    return False


def _session_segments(events: list[TraceEvent]) -> list[list[TraceEvent]]:
    segments: list[list[TraceEvent]] = []
    current: list[TraceEvent] = []
    for event in events:
        if event.event_type == "session_started" and current:
            segments.append(current)
            current = []
        current.append(event)
    if current:
        segments.append(current)
    return segments


def _decision_from_payload(payload: dict, index: int) -> Decision:
    if "kind" not in payload:
        raise UnreplayableTraceError(
            f"decision_made event #{index} missing kind"
        )
    try:
        return Decision(
            kind=payload["kind"],
            tool_name=payload.get("tool_name"),
            tool_args=payload.get("tool_args") or {},
            assistant_message=payload.get("assistant_message"),
        )
    except Exception as exc:
        raise UnreplayableTraceError(
            f"decision_made event #{index} invalid: {exc}"
        ) from exc


def _limits_from_events(events: list[TraceEvent]) -> RuntimeLimits:
    """Restore compaction knobs recorded in ``compaction_started`` events."""

    base = RuntimeLimits()
    for e in events:
        if e.event_type != "compaction_started":
            continue
        payload = e.payload
        overrides: dict[str, int] = {}
        if "threshold_tokens" in payload:
            overrides["compaction_threshold_tokens"] = int(payload["threshold_tokens"])
        if "keep_last" in payload:
            overrides["compaction_keep_last_messages"] = int(payload["keep_last"])
        if overrides:
            return replace(base, **overrides)
    return base


def _drive_loop(
    segments: list[list[TraceEvent]],
    workspace_root: Path | None,
    source_events: list[TraceEvent],
) -> list[TraceEvent]:
    if workspace_root is None:
        with tempfile.TemporaryDirectory() as ws:
            return _run(Path(ws), segments, source_events)
    return _run(workspace_root, segments, source_events)


def _shell_profile_from_segments(segments: list[list[TraceEvent]]) -> str | None:
    for segment in segments:
        for event in segment:
            if event.event_type != "session_started":
                continue
            profile = event.payload.get("shell_profile")
            if profile:
                return str(profile)
    return None


def _run(
    workspace: Path,
    segments: list[list[TraceEvent]],
    source_events: list[TraceEvent],
) -> list[TraceEvent]:
    limits = _limits_from_events(source_events)
    tools = _build_tool_registry(workspace, limits)
    shell_profile = _shell_profile_from_segments(segments)

    session_plans: list[tuple[str, list[TurnPlan]]] = []
    for segment in segments:
        goal = segment[0].payload.get("goal", "") if segment else ""
        session_plans.append((str(goal), _extract_turns(segment)))

    flat_decisions: list[Decision] = [
        d for _, turns in session_plans for _, ds in turns for d in ds
    ]

    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel(decisions=flat_decisions),
        policy=DefaultPolicy(workspace_root=workspace, shell_profile=shell_profile),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        limits=limits,
        memory=InMemoryMemoryStore(),
        workspace_root=workspace,
    )

    for goal, turns in session_plans:
        session = loop.start(goal=goal)
        for user_input, decisions in turns:
            max_steps = max(1, len(decisions))
            loop.run_session(session.id, user_input, max_steps=max_steps)
    return recorder.events
