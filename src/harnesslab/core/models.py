from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class BudgetUsage(BaseModel):
    llm_calls_total: int = 0
    tool_calls_total: int = 0
    tokens_total: int = 0
    wall_time_ms_total: int = 0
    cost_usd_total: float = 0.0
    last_budget_status: Literal["ok", "soft_exceeded", "hard_exceeded"] = "ok"


class ArtifactMeta(BaseModel):
    id: str
    session_id: str
    mime: str
    size_bytes: int
    sha256: str
    created_at: datetime


class Message(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("msg"))
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None
    tool_call_id: str | None = None
    # OpenAI/DeepSeek assistant ``tool_calls`` payload when the loop
    # records a model-initiated tool request before the tool result.
    tool_calls: list[dict[str, Any]] | None = None
    # Provider reasoning captured for replay when the API requires it
    # (e.g. DeepSeek ``reasoning_content`` in a tool loop).
    reasoning_text: str | None = None
    # Opaque vendor payload when normalization would lose data.
    provider_extra: dict[str, Any] | None = None


SessionStatus = Literal[
    "running",
    "waiting_user",
    "done",
    "failed",
    "aborted",
]


class Session(BaseModel):
    """A live or persisted agent session.

    Lifecycle fields (Phase 2.3):

    - ``status`` advances ``running → waiting_user`` when the model
      returns ``ask_user``, and ``running → done`` when it returns
      ``final``. ``failed`` and ``aborted`` are reserved for the loop
      and CLI to set explicitly (later phases).
    - ``turn_count`` counts user inputs the loop has processed; it
      moves forward exactly once per ``run_session`` call.
    - ``step_count`` counts inner-loop iterations (model decisions)
      across the entire session.
    - ``last_step_at`` is refreshed at the end of every step so the
      ``harnesslab session ls`` CLI can show recency.
    - ``parent_session_id`` is set when the session was created by
      forking another session; ``None`` for top-level sessions.
    - ``title`` is a short human-readable label derived from the
      initial goal so ``session ls`` can be skimmed.
    """

    id: str = Field(default_factory=lambda: _new_id("ses"))
    goal: str
    status: SessionStatus = "running"
    messages: list[Message] = Field(default_factory=list)
    turn_count: int = 0
    step_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_step_at: datetime | None = None
    parent_session_id: str | None = None
    title: str | None = None
    model_backend: str | None = None
    model_id: str | None = None
    model_effort: str | None = None
    budget_usage: BudgetUsage = Field(default_factory=BudgetUsage)


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("tool"))
    name: str
    args: dict[str, Any]
    session_id: str | None = None
    policy_decision: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ToolResult(BaseModel):
    ok: bool
    output: str
    error: str | None = None
    artifact_ref: str | None = None


class TraceEvent(BaseModel):
    run_id: str
    session_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


SpanKind = Literal["internal", "client", "server"]
SpanStatus = Literal["ok", "error", "unset"]


class SpanEventRecord(BaseModel):
    name: str
    time: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanLinkRecord(BaseModel):
    trace_id: str
    span_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanRecord(BaseModel):
    """One completed span (Observability v2).

    Normative spec: ``docs/architecture/observability-v2.md`` § D6.
    """

    resource: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: SpanKind = "internal"
    session_id: str
    turn_index: int
    start_time: datetime
    end_time: datetime
    duration_ms: float
    status: SpanStatus = "ok"
    status_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[SpanEventRecord] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    links: list[SpanLinkRecord] = Field(default_factory=list)


class SpanHandle(BaseModel):
    """Opaque span reference returned by ``SpanRecorderPort.start_span``."""

    model_config = {"frozen": True}

    trace_id: str
    span_id: str
    session_id: str
    turn_index: int
    name: str


class Decision(BaseModel):
    """A single step's model decision.

    Kinds:

    - ``tool``: invoke ``tool_name`` with ``tool_args``; the loop appends
      the tool result and continues to the next step.
    - ``assistant``: intermediate narration; the loop appends the
      assistant message and continues to the next step.
    - ``plan``: intermediate planning output; the loop appends the
      assistant message marked with ``provider_extra.is_plan=true`` and
      continues to the next step.
    - ``final``: terminal answer; the loop appends the assistant message
      and stops with ``session_finished(reason="final")``.
    - ``ask_user``: terminal pause awaiting more user input; the loop
      appends the assistant message and stops with
      ``session_finished(reason="ask_user")``.
    """

    kind: Literal["assistant", "plan", "tool", "final", "ask_user"]
    assistant_message: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)


TERMINAL_DECISION_KINDS: frozenset[str] = frozenset({"final", "ask_user"})
