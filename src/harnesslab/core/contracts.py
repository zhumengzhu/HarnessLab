from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from harnesslab.core.models import Decision, Session, ToolCall, ToolResult, TraceEvent


class ModelPort(Protocol):
    def decide(self, session: Session, user_input: str) -> Decision: ...


class ToolPort(Protocol):
    name: str
    description: str
    args_schema: dict[str, Any]

    def execute(self, call: ToolCall) -> ToolResult: ...


class PolicyPort(Protocol):
    def allow_tool(self, call: ToolCall) -> tuple[bool, str]: ...


class SessionStorePort(Protocol):
    def create(self, session: Session) -> None: ...

    def get(self, session_id: str) -> Session: ...

    def save(self, session: Session) -> None: ...


class MemoryStorePort(Protocol):
    def put(self, key: str, value: str) -> None: ...

    def get(self, key: str) -> str | None: ...


class TraceRecorderPort(Protocol):
    def record(self, event: TraceEvent) -> None: ...


class ClockPort(Protocol):
    """Time source. Injected so replay/tests can use deterministic clocks."""

    def now(self) -> datetime: ...


class IdPort(Protocol):
    """ID source. Injected so replay/tests can use deterministic IDs."""

    def new_id(self, prefix: str) -> str: ...


class RuntimeContext(Protocol):
    workspace_root: Path
