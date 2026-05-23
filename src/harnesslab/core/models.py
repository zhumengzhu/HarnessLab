from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Message(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("msg"))
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None
    tool_call_id: str | None = None


class Session(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ses"))
    goal: str
    status: Literal["running", "done", "failed"] = "running"
    messages: list[Message] = Field(default_factory=list)
    turn_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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


class TraceEvent(BaseModel):
    run_id: str
    session_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Decision(BaseModel):
    """A single step's model decision.

    Kinds:

    - ``tool``: invoke ``tool_name`` with ``tool_args``; the loop appends
      the tool result and continues to the next step.
    - ``assistant``: intermediate narration; the loop appends the
      assistant message and continues to the next step.
    - ``final``: terminal answer; the loop appends the assistant message
      and stops with ``session_finished(reason="final")``.
    - ``ask_user``: terminal pause awaiting more user input; the loop
      appends the assistant message and stops with
      ``session_finished(reason="ask_user")``.
    """

    kind: Literal["assistant", "tool", "final", "ask_user"]
    assistant_message: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)


TERMINAL_DECISION_KINDS: frozenset[str] = frozenset({"final", "ask_user"})
