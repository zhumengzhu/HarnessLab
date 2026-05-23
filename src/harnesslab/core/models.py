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
    kind: Literal["assistant", "tool"]
    assistant_message: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
