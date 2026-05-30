"""Loop-facing span instrumentation helpers (Observability v2 O3)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from harnesslab.core.contracts import SpanRecorderPort
from harnesslab.core.models import Session, SpanHandle
from harnesslab.core.trace_scope import trace_scope
from harnesslab.telemetry.span_attributes import (
    GEN_AI_REQUEST_MODEL,
    GEN_AI_SYSTEM,
    HARNESSLAB_COMPACTION_KEEP_LAST,
    HARNESSLAB_COMPACTION_MESSAGES_AFTER,
    HARNESSLAB_COMPACTION_MESSAGES_BEFORE,
    HARNESSLAB_COMPACTION_THRESHOLD_TOKENS,
    HARNESSLAB_COMPACTION_TRIGGER,
    HARNESSLAB_DECISION_KIND,
    HARNESSLAB_FAILOVER_ATTEMPTS,
    HARNESSLAB_MAX_STEPS,
    HARNESSLAB_PARENT_SESSION_ID,
    HARNESSLAB_SESSION_GOAL,
    HARNESSLAB_SHELL_PROFILE,
    HARNESSLAB_SKILL_COMMAND,
    HARNESSLAB_SKILL_NAME,
    HARNESSLAB_SKILL_TASK_PREVIEW,
    HARNESSLAB_STEP_INDEX,
    HARNESSLAB_STEP_OUTCOME,
    HARNESSLAB_STEP_REASON,
    HARNESSLAB_STEPS_USED,
    HARNESSLAB_TERMINAL_REASON,
    HARNESSLAB_THINKING_ENABLED,
    HARNESSLAB_USER_INPUT_PREVIEW,
    SPAN_CONTEXT_COMPACT,
    SPAN_LLM_GENERATE,
    SPAN_LLM_TITLE,
    SPAN_SKILL_COMMAND,
    SPAN_SKILL_INVOKE,
    SPAN_SLASH_REMEMBER,
    SPAN_STEP,
    SPAN_SUB_AGENT_RUN,
    SPAN_TURN,
)
from harnesslab.telemetry.trace_ids import new_trace_id

_log = logging.getLogger(__name__)


def preview_text(raw: str, limit: int = 256) -> str:
    text = " ".join(str(raw).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


class LoopSpans:
    """Manage span hierarchy for ``HarnessLoop``."""

    def __init__(self, recorder: SpanRecorderPort) -> None:
        self._recorder = recorder
        self._turn_stack: list[SpanHandle] = []
        self._step_stack: list[SpanHandle] = []
        self._tool: SpanHandle | None = None
        self._skill_invoke: SpanHandle | None = None
        self._pending_child_turn_root: SpanHandle | None = None

    @property
    def turn(self) -> SpanHandle | None:
        return self._turn_stack[-1] if self._turn_stack else None

    @property
    def active_step(self) -> SpanHandle | None:
        return self._step_stack[-1] if self._step_stack else None

    def _pop_turn(self, handle: SpanHandle) -> None:
        if self._turn_stack and self._turn_stack[-1] is handle:
            self._turn_stack.pop()

    def _pop_step(self, handle: SpanHandle) -> None:
        if self._step_stack and self._step_stack[-1] is handle:
            self._step_stack.pop()

    @property
    def active_tool(self) -> SpanHandle | None:
        return self._tool

    def finish_turn(
        self,
        handle: SpanHandle,
        *,
        terminal_reason: str,
        steps_used: int,
    ) -> None:
        self._recorder.end_span(
            handle,
            attributes={
                HARNESSLAB_TERMINAL_REASON: terminal_reason,
                HARNESSLAB_STEPS_USED: steps_used,
            },
        )
        self._pop_turn(handle)

    @contextmanager
    def turn_scope(
        self,
        session: Session,
        *,
        user_input: str,
        max_steps: int,
        shell_profile: str | None = None,
    ) -> Iterator[SpanHandle]:
        attrs: dict[str, Any] = {
            HARNESSLAB_SESSION_GOAL: preview_text(session.goal),
            HARNESSLAB_USER_INPUT_PREVIEW: preview_text(user_input),
            HARNESSLAB_MAX_STEPS: max_steps,
        }
        if shell_profile:
            attrs[HARNESSLAB_SHELL_PROFILE] = shell_profile
        if session.parent_session_id:
            attrs[HARNESSLAB_PARENT_SESSION_ID] = session.parent_session_id
        handle = self._recorder.start_span(
            SPAN_TURN,
            session_id=session.id,
            trace_id=new_trace_id(),
            turn_index=session.turn_count,
            attributes=attrs,
        )
        self._turn_stack.append(handle)
        if session.turn_count == 0:
            self._recorder.add_span_event(handle, "session.created", {"goal": session.goal})
        try:
            yield handle
        except Exception as exc:
            self._recorder.end_span(handle, status="error", status_message=str(exc))
            raise
        finally:
            if self._turn_stack and self._turn_stack[-1] is handle:
                try:
                    self._recorder.end_span(
                        handle,
                        status="error",
                        status_message="turn scope exited without finish_turn",
                        attributes={
                            HARNESSLAB_TERMINAL_REASON: "incomplete",
                        },
                    )
                except RuntimeError as exc:
                    _log.warning(
                        "could not close turn span for session %s: %s",
                        session.id,
                        exc,
                    )
            self._pop_turn(handle)

    @contextmanager
    def skill_invoke(
        self,
        session: Session,
        *,
        skill_name: str,
        task: str,
    ) -> Iterator[SpanHandle]:
        parent = self.turn
        if parent is None:
            raise RuntimeError("skill invoke requires active turn")
        with trace_scope(
            self._recorder,
            SPAN_SKILL_INVOKE,
            session_id=session.id,
            parent=parent,
            attributes={
                HARNESSLAB_SKILL_NAME: skill_name,
                HARNESSLAB_SKILL_TASK_PREVIEW: preview_text(task),
            },
        ) as handle:
            self._skill_invoke = handle
            try:
                yield handle
            finally:
                self._skill_invoke = None

    @contextmanager
    def step(
        self,
        session: Session,
        *,
        step_index: int,
        reason: str,
    ) -> Iterator[SpanHandle]:
        parent = self._skill_invoke or self.turn
        if parent is None:
            raise RuntimeError("step span requires active turn")
        handle = self._recorder.start_span(
            SPAN_STEP,
            session_id=session.id,
            parent=parent,
            attributes={
                HARNESSLAB_STEP_INDEX: step_index,
                HARNESSLAB_STEP_REASON: reason,
            },
        )
        self._step_stack.append(handle)
        try:
            yield handle
        except Exception as exc:
            self._recorder.end_span(handle, status="error", status_message=str(exc))
            raise
        finally:
            self._pop_step(handle)

    def finish_step(self, handle: SpanHandle, *, outcome: str) -> None:
        self._recorder.end_span(handle, attributes={HARNESSLAB_STEP_OUTCOME: outcome})
        self._pop_step(handle)

    @contextmanager
    def llm_generate(
        self,
        session: Session,
        *,
        step_index: int,
        thinking_likely: bool,
    ) -> Iterator[SpanHandle]:
        parent = self.active_step or self._skill_invoke or self.turn
        if parent is None:
            raise RuntimeError("llm span requires active turn/step")
        handle = self._recorder.start_span(
            SPAN_LLM_GENERATE,
            session_id=session.id,
            parent=parent,
            kind="client",
            attributes={
                HARNESSLAB_STEP_INDEX: step_index,
                HARNESSLAB_THINKING_ENABLED: thinking_likely,
            },
        )
        try:
            yield handle
        except Exception as exc:
            self._recorder.end_span(handle, status="error", status_message=str(exc))
            raise

    def finish_llm_generate(
        self,
        handle: SpanHandle,
        *,
        decision_kind: str,
        metrics: dict[str, Any],
        provider: str | None = None,
        model_id: str | None = None,
        failover_attempts: int = 0,
        status: str = "ok",
        status_message: str | None = None,
    ) -> None:
        attrs: dict[str, Any] = {HARNESSLAB_DECISION_KIND: decision_kind}
        if provider:
            attrs[GEN_AI_SYSTEM] = provider
        if model_id:
            attrs[GEN_AI_REQUEST_MODEL] = model_id
        if failover_attempts > 0:
            attrs[HARNESSLAB_FAILOVER_ATTEMPTS] = failover_attempts
        self._recorder.end_span(
            handle,
            status="error" if status == "error" else "ok",
            status_message=status_message,
            attributes=attrs,
            metrics=metrics,
        )

    @contextmanager
    def llm_title(
        self,
        session: Session,
        *,
        parent: SpanHandle | None = None,
    ) -> Iterator[SpanHandle]:
        turn = parent or self.turn
        if turn is None:
            raise RuntimeError("title span requires active turn")
        with trace_scope(
            self._recorder,
            SPAN_LLM_TITLE,
            session_id=session.id,
            parent=turn,
            kind="client",
        ) as handle:
            yield handle

    @contextmanager
    def tool(
        self,
        session: Session,
        *,
        tool_name: str,
        tool_call_id: str,
    ) -> Iterator[SpanHandle]:
        parent = self.active_step or self.turn
        if parent is None:
            raise RuntimeError("tool span requires active step/turn")
        handle = self._recorder.start_span(
            f"tool.{tool_name}",
            session_id=session.id,
            parent=parent,
            attributes={
                "harnesslab.tool.name": tool_name,
                "harnesslab.tool_call.id": tool_call_id,
            },
        )
        self._tool = handle
        try:
            yield handle
        except Exception as exc:
            self._recorder.end_span(handle, status="error", status_message=str(exc))
            raise
        finally:
            if self._tool is handle:
                self._tool = None

    def finish_tool(
        self,
        handle: SpanHandle,
        *,
        ok: bool,
        policy_decision: str | None,
        metrics: dict[str, Any],
        status_message: str | None = None,
    ) -> None:
        attrs: dict[str, Any] = {
            "harnesslab.tool.ok": ok,
        }
        if policy_decision:
            attrs["harnesslab.policy.decision"] = policy_decision
        self._recorder.end_span(
            handle,
            status="ok" if ok else "error",
            status_message=status_message,
            attributes=attrs,
            metrics=metrics,
        )

    def tool_event(
        self,
        handle: SpanHandle,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._recorder.add_span_event(handle, name, attributes=attributes)

    @contextmanager
    def tool_phase(
        self,
        session: Session,
        *,
        tool_name: str,
        phase: str,
        parent: SpanHandle,
        hook_name: str | None = None,
        hook_type: str | None = None,
    ) -> Iterator[SpanHandle]:
        span_name = f"tool.hooks.{phase}"
        attrs: dict[str, Any] = {
            "harnesslab.tool.name": tool_name,
            "harnesslab.hook.phase": f"{phase}_tool",
        }
        if hook_name:
            attrs["harnesslab.hook.name"] = hook_name
        if hook_type:
            attrs["harnesslab.hook.type"] = hook_type
        with trace_scope(
            self._recorder,
            span_name,
            session_id=session.id,
            parent=parent,
            attributes=attrs,
        ) as handle:
            yield handle

    @contextmanager
    def compact(
        self,
        session: Session,
        *,
        parent: SpanHandle,
        trigger: str,
        keep_last: int,
        messages_before: int,
        threshold_tokens: int | None = None,
    ) -> Iterator[SpanHandle]:
        attrs: dict[str, Any] = {
            HARNESSLAB_COMPACTION_TRIGGER: trigger,
            HARNESSLAB_COMPACTION_KEEP_LAST: keep_last,
            HARNESSLAB_COMPACTION_MESSAGES_BEFORE: messages_before,
        }
        if threshold_tokens is not None:
            attrs[HARNESSLAB_COMPACTION_THRESHOLD_TOKENS] = threshold_tokens
        handle = self._recorder.start_span(
            SPAN_CONTEXT_COMPACT,
            session_id=session.id,
            parent=parent,
            attributes=attrs,
        )
        try:
            yield handle
        except Exception as exc:
            self._recorder.end_span(handle, status="error", status_message=str(exc))
            raise

    def finish_compact(
        self,
        handle: SpanHandle,
        *,
        messages_after: int,
        metrics: dict[str, Any],
    ) -> None:
        self._recorder.end_span(
            handle,
            attributes={HARNESSLAB_COMPACTION_MESSAGES_AFTER: messages_after},
            metrics=metrics,
        )

    @contextmanager
    def slash_remember(self, session: Session) -> Iterator[SpanHandle]:
        parent = self.turn
        if parent is None:
            raise RuntimeError("remember span requires active turn")
        with trace_scope(
            self._recorder,
            SPAN_SLASH_REMEMBER,
            session_id=session.id,
            parent=parent,
        ) as handle:
            yield handle

    @contextmanager
    def skill_command(self, session: Session, *, command: str) -> Iterator[SpanHandle]:
        parent = self.turn
        if parent is None:
            raise RuntimeError("skill command span requires active turn")
        with trace_scope(
            self._recorder,
            SPAN_SKILL_COMMAND,
            session_id=session.id,
            parent=parent,
            attributes={HARNESSLAB_SKILL_COMMAND: command},
        ) as handle:
            yield handle

    @contextmanager
    def sub_agent_run(
        self,
        session: Session,
        *,
        parent_tool: SpanHandle,
        goal: str,
        max_steps: int,
    ) -> Iterator[SpanHandle]:
        handle = self._recorder.start_span(
            SPAN_SUB_AGENT_RUN,
            session_id=session.id,
            parent=parent_tool,
            attributes={
                "harnesslab.sub_agent.goal": preview_text(goal),
                "harnesslab.sub_agent.max_steps": max_steps,
            },
        )
        try:
            yield handle
        except Exception as exc:
            self._recorder.end_span(handle, status="error", status_message=str(exc))
            raise

    def finish_sub_agent_run(
        self,
        handle: SpanHandle,
        *,
        child_session_id: str,
        ok: bool,
        metrics: dict[str, Any],
    ) -> None:
        self._recorder.end_span(
            handle,
            status="ok" if ok else "error",
            attributes={"harnesslab.child_session.id": child_session_id},
            metrics=metrics,
        )

    def add_step_event(
        self,
        session: Session,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        target = self.active_step or self.turn
        if target is None:
            return
        self._recorder.add_span_event(target, name, attributes=attributes)

    def link_sub_agent(
        self,
        parent: SpanHandle,
        *,
        child_turn_root: SpanHandle,
        child_session_id: str,
    ) -> None:
        self._recorder.add_span_link(
            parent,
            linked_trace_id=child_turn_root.trace_id,
            linked_span_id=child_turn_root.span_id,
            attributes={
                "harnesslab.link.kind": "sub_agent",
                "harnesslab.child_session.id": child_session_id,
            },
        )

    def store_child_turn_root(self, handle: SpanHandle) -> None:
        self._pending_child_turn_root = handle

    def consume_child_turn_root(self) -> SpanHandle | None:
        handle = self._pending_child_turn_root
        self._pending_child_turn_root = None
        return handle
