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
from pathlib import Path

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, TraceEvent
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.shell_tool import RunShellSafeTool


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

    goal = events[0].payload.get("goal", "")
    turns = _extract_turns(events)
    return _drive_loop(goal, turns, workspace_root)


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
            raise UnreplayableTraceError(
                f"user_input_received at #{i} not followed by any decision_made"
            )
        turns.append((user_input, decisions))
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


def _drive_loop(
    goal: str,
    turns: list[TurnPlan],
    workspace_root: Path | None,
) -> list[TraceEvent]:
    if workspace_root is None:
        with tempfile.TemporaryDirectory() as ws:
            return _run(Path(ws), goal, turns)
    return _run(workspace_root, goal, turns)


def _run(
    workspace: Path,
    goal: str,
    turns: list[TurnPlan],
) -> list[TraceEvent]:
    limits = RuntimeLimits()
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace, limits=limits))
    tools.register(WriteFileTool(workspace, limits=limits))
    tools.register(RunShellSafeTool(workspace, limits=limits))

    flat_decisions: list[Decision] = [d for _, ds in turns for d in ds]

    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel(decisions=flat_decisions),
        policy=DefaultPolicy(workspace_root=workspace),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
    )

    session = loop.start(goal=goal)
    for user_input, decisions in turns:
        loop.run_session(session.id, user_input, max_steps=len(decisions))
    return recorder.events
