"""Deterministic single-session replay of a JSONL trace.

The replayer extracts the user-input + decision pairs from a trace,
constructs a `ReplayModel` over those decisions, runs the loop end-to-end
with a `FrozenClock` + `SeqIdProvider`, and returns the freshly recorded
trace events. Callers then hand both event lists to `detect_divergence`.
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


def replay_session(
    events: list[TraceEvent],
    workspace_root: Path | None = None,
) -> list[TraceEvent]:
    """Replay one single-session event sequence; return the new trace.

    The caller is responsible for splitting multi-session traces with
    `group_by_session` before calling this function. When
    ``workspace_root`` is None, a fresh tmp dir is used; this keeps
    replay hermetic for tasks that only touch their own workspace
    (e.g. write_then_read).
    """

    if not events:
        raise UnreplayableTraceError("trace is empty")
    if events[0].event_type != "session_started":
        raise UnreplayableTraceError(
            f"first event must be session_started, got {events[0].event_type!r}"
        )

    goal = events[0].payload.get("goal", "")
    inputs, decisions = _extract_turns(events)
    return _drive_loop(goal, inputs, decisions, workspace_root)


def _extract_turns(
    events: list[TraceEvent],
) -> tuple[list[str], list[Decision]]:
    inputs: list[str] = []
    decisions: list[Decision] = []
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
        if i + 1 >= len(events) or events[i + 1].event_type != "decision_made":
            raise UnreplayableTraceError(
                f"user_input_received at #{i} not followed by decision_made"
            )
        decision = _decision_from_payload(events[i + 1].payload, index=i + 1)
        inputs.append(user_input)
        decisions.append(decision)
        i += 2
    return inputs, decisions


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
    inputs: list[str],
    decisions: list[Decision],
    workspace_root: Path | None,
) -> list[TraceEvent]:
    if workspace_root is None:
        with tempfile.TemporaryDirectory() as ws:
            return _run(Path(ws), goal, inputs, decisions)
    return _run(workspace_root, goal, inputs, decisions)


def _run(
    workspace: Path,
    goal: str,
    inputs: list[str],
    decisions: list[Decision],
) -> list[TraceEvent]:
    limits = RuntimeLimits()
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace, limits=limits))
    tools.register(WriteFileTool(workspace, limits=limits))
    tools.register(RunShellSafeTool(workspace, limits=limits))

    recorder = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=ReplayModel(decisions=decisions),
        policy=DefaultPolicy(workspace_root=workspace),
        sessions=InMemorySessionStore(),
        tools=tools,
        trace=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
    )

    session = loop.start(goal=goal)
    for user_input in inputs:
        loop.run_turn(session.id, user_input)
    return recorder.events
