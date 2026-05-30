from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from harnesslab.core.models import (
    ArtifactMeta,
    Decision,
    Session,
    SpanHandle,
    SpanKind,
    SpanRecord,
    SpanStatus,
    ToolCall,
    ToolResult,
)


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
        parent_session_id: str | None = None,
    ) -> list[Session]:
        """Return sessions newest-first, optionally filtered by ``status``
        or ``parent_session_id``.

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


class SpanRecorderPort(Protocol):
    """Span lifecycle telemetry (Observability v2).

    See ``docs/architecture/observability-v2.md`` § D4.
    """

    def start_span(
        self,
        name: str,
        *,
        session_id: str,
        kind: SpanKind = "internal",
        attributes: dict[str, Any] | None = None,
        parent: SpanHandle | None = None,
        trace_id: str | None = None,
        turn_index: int | None = None,
    ) -> SpanHandle: ...

    def end_span(
        self,
        handle: SpanHandle,
        *,
        status: SpanStatus = "ok",
        status_message: str | None = None,
        attributes: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> SpanRecord: ...

    def add_span_event(
        self,
        handle: SpanHandle,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None: ...

    def add_span_link(
        self,
        handle: SpanHandle,
        *,
        linked_trace_id: str,
        linked_span_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> None: ...

    def current_span(self, session_id: str) -> SpanHandle | None: ...


class ClockPort(Protocol):
    """Time source. Injected so replay/tests can use deterministic clocks."""

    def now(self) -> datetime: ...


class IdPort(Protocol):
    """ID source. Injected so replay/tests can use deterministic IDs."""

    def new_id(self, prefix: str) -> str: ...


class RuntimeContext(Protocol):
    workspace_root: Path
