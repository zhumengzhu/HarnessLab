"""Run a TaskSuite against the production loop and produce TaskResults.

Each task runs in its own temporary workspace with a fresh ``FrozenClock``
and ``SeqIdProvider`` so that trace IDs, timestamps, and duration_ms are
fully deterministic across machines.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import TraceEvent
from harnesslab.core.replay import ReplayModel, ReplayTraceRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.eval.task import (
    ExpectedEvent,
    Task,
    TaskMetrics,
    TaskResult,
    TaskSuite,
)
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.shell_tool import RunShellSafeTool


def _payload_contains(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Recursive subset match: every (k, v) in expected must equal in actual."""

    for k, v in expected.items():
        if k not in actual:
            return False
        if isinstance(v, dict) and isinstance(actual[k], dict):
            if not _payload_contains(actual[k], v):
                return False
        elif actual[k] != v:
            return False
    return True


def _evaluate(task: Task, events: list[TraceEvent], final_reply: str) -> TaskResult:
    failures: list[str] = []

    for needle in task.expected.final_reply_contains:
        if needle not in final_reply:
            failures.append(f"final reply missing substring: {needle!r}")

    cursor = 0
    for expected in task.expected.events_include:
        matched_at = _find_event(events, expected, start=cursor)
        if matched_at == -1:
            failures.append(_format_missing_event(expected))
        else:
            cursor = matched_at + 1

    actual_types = {e.event_type for e in events}
    for forbidden in task.expected.no_event_types:
        if forbidden in actual_types:
            failures.append(f"forbidden event type appeared: {forbidden}")

    metrics = TaskMetrics(
        turns=len(task.turns),
        tool_calls=sum(1 for e in events if e.event_type == "tool_executed"),
        tool_failures=sum(
            1
            for e in events
            if e.event_type == "tool_executed" and not e.payload.get("ok", True)
        ),
        denials=sum(1 for e in events if e.event_type == "tool_denied"),
        invalid_args=sum(1 for e in events if e.event_type == "tool_invalid_args"),
    )

    return TaskResult(
        task_name=task.name,
        passed=not failures,
        failures=failures,
        metrics=metrics,
        final_reply=final_reply,
    )


def _find_event(events: list[TraceEvent], expected: ExpectedEvent, start: int) -> int:
    for i in range(start, len(events)):
        actual = events[i]
        if actual.event_type != expected.event_type:
            continue
        if expected.payload_contains is not None and not _payload_contains(
            actual.payload, expected.payload_contains
        ):
            continue
        return i
    return -1


def _format_missing_event(expected: ExpectedEvent) -> str:
    if expected.payload_contains:
        return (
            f"expected event not found in order: {expected.event_type} "
            f"with payload containing {expected.payload_contains}"
        )
    return f"expected event not found in order: {expected.event_type}"


class TaskRunner:
    """Drive HarnessLoop end-to-end for each task, in isolation."""

    def __init__(self, clock_start: datetime | None = None) -> None:
        self._clock_start = clock_start or DEFAULT_REPLAY_CLOCK_START

    def run(self, suite: TaskSuite) -> list[TaskResult]:
        return [self.run_one(t) for t in suite.tasks]

    def run_one(self, task: Task) -> TaskResult:
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            events, final_reply = self._drive_loop(task, workspace)
            return _evaluate(task, events, final_reply)

    def _drive_loop(
        self, task: Task, workspace: Path
    ) -> tuple[list[TraceEvent], str]:
        limits = RuntimeLimits()
        tools = ToolRegistry()
        tools.register(ReadFileTool(workspace, limits=limits))
        tools.register(WriteFileTool(workspace, limits=limits))
        tools.register(RunShellSafeTool(workspace, limits=limits))

        recorder = ReplayTraceRecorder()
        model: Any = (
            ReplayModel(decisions=task.decisions) if task.decisions else SimpleModel()
        )

        loop = HarnessLoop(
            model=model,
            policy=DefaultPolicy(workspace_root=workspace),
            sessions=InMemorySessionStore(),
            tools=tools,
            trace=recorder,
            clock=FrozenClock(start=self._clock_start),
            ids=SeqIdProvider(),
        )

        session = loop.start(goal=task.goal)
        replies = _drive_turns(loop, session.id, task.turns)
        final_reply = replies[-1] if replies else ""
        return recorder.events, final_reply


def _drive_turns(loop: HarnessLoop, session_id: str, turns: Iterable[Any]) -> list[str]:
    replies: list[str] = []
    for turn in turns:
        replies.append(loop.run_turn(session_id, turn.input))
    return replies
