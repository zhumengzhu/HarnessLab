"""Data model for eval tasks, suites, and per-task results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from harnesslab.core.models import Decision


class ExpectedEvent(BaseModel):
    """A single trace-event expectation.

    `event_type` must match exactly. `payload_contains` is a (possibly
    nested) subset check against the actual event payload: every key
    declared here must appear in the actual payload with an equal value.
    """

    event_type: str
    payload_contains: dict[str, Any] | None = None


class TaskTurn(BaseModel):
    input: str


class TaskExpected(BaseModel):
    final_reply_contains: list[str] = Field(default_factory=list)
    events_include: list[ExpectedEvent] = Field(default_factory=list)
    no_event_types: list[str] = Field(default_factory=list)


class Task(BaseModel):
    name: str
    goal: str
    description: str = ""
    decisions: list[Decision] | None = None
    turns: list[TaskTurn]
    expected: TaskExpected = Field(default_factory=TaskExpected)


class TaskSuite(BaseModel):
    tasks: list[Task]


class TaskMetrics(BaseModel):
    turns: int
    tool_calls: int  # tool_executed events
    tool_failures: int  # tool_executed events with ok=false
    denials: int  # tool_denied events
    invalid_args: int  # tool_invalid_args events


class TaskResult(BaseModel):
    task_name: str
    passed: bool
    failures: list[str]
    metrics: TaskMetrics
    final_reply: str
