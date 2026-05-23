from __future__ import annotations

from pathlib import Path
from typing import Protocol

from harnesslab.core.models import Decision, Session, ToolCall, ToolResult, TraceEvent


class ModelPort(Protocol):
    def decide(self, session: Session, user_input: str) -> Decision: ...


class ToolPort(Protocol):
    name: str

    def execute(self, call: ToolCall) -> ToolResult: ...


class PolicyPort(Protocol):
    def allow_tool(self, call: ToolCall) -> tuple[bool, str]: ...


class SessionStorePort(Protocol):
    def create(self, goal: str) -> Session: ...

    def get(self, session_id: str) -> Session: ...

    def save(self, session: Session) -> None: ...


class MemoryStorePort(Protocol):
    def put(self, key: str, value: str) -> None: ...

    def get(self, key: str) -> str | None: ...


class TraceRecorderPort(Protocol):
    def record(self, event: TraceEvent) -> None: ...


class RuntimeContext(Protocol):
    workspace_root: Path
