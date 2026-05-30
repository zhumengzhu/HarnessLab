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
    # Inner-loop step budget for this turn. Defaults to 1 to preserve the
    # original single-step contract used by existing eval tasks; raise to
    # let the model react to tool results inside the same turn.
    max_steps: int = 1
    # When true, start a fresh session before this turn (cross-session eval).
    new_session: bool = False
    goal: str | None = None


class TaskLimits(BaseModel):
    """Optional runtime limit overrides for a single eval task.

    Used to exercise compaction with a low token threshold without
    changing global defaults.
    """

    compaction_threshold_tokens: int | None = None
    compaction_keep_last_messages: int | None = None
    context_window_tokens: int | None = None
    output_bytes_cap: int | None = None
    shell_timeout_seconds: int | None = None


class TaskPolicy(BaseModel):
    """Per-task policy overrides (eval / isolated runs)."""

    shell_profile: str | None = None


class TaskBudget(BaseModel):
    """Optional budget overrides for a single eval task."""

    enabled: bool = False
    soft_ratio: float = 0.8
    max_session_cost_usd_total: float | None = None
    action_on_hard: str = "final"


class TaskExpected(BaseModel):
    final_reply_contains: list[str] = Field(default_factory=list)
    events_include: list[ExpectedEvent] = Field(default_factory=list)
    no_event_types: list[str] = Field(default_factory=list)


class Task(BaseModel):
    name: str
    goal: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    decisions: list[Decision] | None = None
    turns: list[TaskTurn]
    limits: TaskLimits | None = None
    policy: TaskPolicy | None = None
    budget: TaskBudget | None = None
    replay_call_meta: dict[str, Any] | None = None
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
