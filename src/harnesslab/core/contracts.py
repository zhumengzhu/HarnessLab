from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from harnesslab.core.models import ArtifactMeta, Decision, Session, ToolCall, ToolResult, TraceEvent


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

    def list(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
    ) -> list[Session]:
        """Return sessions newest-first, optionally filtered by ``status``.

        Backends MAY load each row's messages eagerly or lazily; callers
        should not depend on messages being populated in list results.
        """
        ...


class MemoryStorePort(Protocol):
    def put(self, key: str, value: str) -> None: ...

    def get(self, key: str) -> str | None: ...


class SemanticMemoryStorePort(Protocol):
    def upsert(self, key: str, text: str, metadata: dict[str, Any] | None = None) -> None: ...

    def search(self, query: str, k: int = 5) -> list[Any]: ...

    def get(self, key: str) -> str | None: ...


class ArtifactStorePort(Protocol):
    def put(self, data: bytes, *, mime: str, session_id: str, artifact_id: str) -> str: ...

    def get(self, ref: str) -> bytes: ...

    def metadata(self, ref: str) -> ArtifactMeta: ...

    def list(self, *, session_id: str | None = None, limit: int = 50) -> list[ArtifactMeta]: ...


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
