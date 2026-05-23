from __future__ import annotations

from datetime import datetime

from harnesslab.core.compaction import (
    ModelOverflowError,
    Summarizer,
    compact_messages,
    estimate_messages_tokens,
    should_compact,
)
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.context import (
    make_conversation_snapshot,
    merge_adapter_breakdown,
)
from harnesslab.core.contracts import (
    ClockPort,
    IdPort,
    ModelPort,
    PolicyPort,
    SessionStorePort,
    TraceRecorderPort,
)
from harnesslab.core.models import (
    TERMINAL_DECISION_KINDS,
    Decision,
    Message,
    Session,
    ToolCall,
    ToolResult,
    TraceEvent,
)
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.tools.registry import ToolRegistry

_TRACE_OUTPUT_PREVIEW_BYTES = 512

DEFAULT_MAX_STEPS = 20


class HarnessLoop:
    """Orchestrate one session's interaction with the model and tools.

    The public surface is two methods:

    - :meth:`run_turn` runs a single decision step (backwards-compatible
      with the original one-step loop; equivalent to
      ``run_session(..., max_steps=1)``).
    - :meth:`run_session` runs the autonomous inner loop: it keeps calling
      the model — feeding tool results back in via ``session.messages`` —
      until the model returns a terminal decision (``final`` or
      ``ask_user``) or ``max_steps`` is exhausted.
    """

    def __init__(
        self,
        model: ModelPort,
        policy: PolicyPort,
        sessions: SessionStorePort,
        tools: ToolRegistry,
        trace: TraceRecorderPort,
        clock: ClockPort | None = None,
        ids: IdPort | None = None,
        limits: RuntimeLimits | None = None,
        summarizer: Summarizer | None = None,
    ) -> None:
        self._model = model
        self._policy = policy
        self._sessions = sessions
        self._tools = tools
        self._trace = trace
        self._clock: ClockPort = clock or SystemClock()
        self._ids: IdPort = ids or UuidIdProvider()
        self._limits: RuntimeLimits = limits or RuntimeLimits()
        self._summarizer: Summarizer | None = summarizer

    def start(self, goal: str) -> Session:
        session = Session(
            id=self._ids.new_id("ses"),
            goal=goal,
            created_at=self._clock.now(),
            title=_derive_title(goal),
        )
        self._sessions.create(session)
        self._record(
            session=session,
            event_type="session_started",
            payload={"goal": goal},
        )
        return session

    def fork(self, source_id: str, *, goal: str | None = None) -> Session:
        """Create a new session seeded from ``source_id``'s messages.

        The forked session keeps a pointer back to its source via
        ``parent_session_id`` so the ``session show --history`` view
        can walk the lineage. The conversation is copied by value so
        edits to the fork do not mutate the parent.
        """

        parent = self._sessions.get(source_id)
        forked_id = self._ids.new_id("ses")
        # Each ``messages.id`` is a globally unique PRIMARY KEY in the
        # SQLite store, so copied-by-value messages need fresh ids and
        # session_id pointers.
        copied_messages = [
            m.model_copy(
                update={
                    "id": self._ids.new_id("msg"),
                    "session_id": forked_id,
                }
            )
            for m in parent.messages
        ]
        forked = Session(
            id=forked_id,
            goal=goal or parent.goal,
            created_at=self._clock.now(),
            title=_derive_title(goal or parent.goal),
            parent_session_id=parent.id,
            messages=copied_messages,
        )
        self._sessions.create(forked)
        self._record(
            session=forked,
            event_type="session_started",
            payload={"goal": forked.goal, "parent_session_id": parent.id},
        )
        return forked

    def run_turn(self, session_id: str, user_input: str) -> str:
        """Run exactly one decision step.

        Equivalent to ``run_session(..., max_steps=1)``. Kept as the
        narrow surface used by eval tasks and tests that want
        deterministic, single-step trace shapes.
        """

        return self.run_session(session_id, user_input, max_steps=1)

    def run_session(
        self,
        session_id: str,
        user_input: str,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> str:
        """Drive the model/tool loop until terminal or ``max_steps``.

        The model is consulted once per step. After a non-terminal
        decision (``tool`` or ``assistant``), the loop appends the
        relevant message to ``session.messages`` and calls the model
        again so it can react to the new state. The empty string is
        passed as ``user_input`` to follow-up calls; real model adapters
        rely on ``session.messages`` for the new signal, and
        ``SimpleModel`` falls through to its canned final response.
        """

        if max_steps < 1:
            raise ValueError(f"max_steps must be >= 1, got {max_steps}")

        session = self._sessions.get(session_id)
        session.status = "running"
        self._record(
            session=session,
            event_type="user_input_received",
            payload={
                "turn_index": session.turn_count,
                "user_input": user_input,
            },
        )
        session.messages.append(
            self._make_message(role="user", content=user_input, session=session)
        )

        last_response = ""
        terminal_reason = "max_steps"
        steps_used = 0
        prev_terminal: str | None = None

        for step_index in range(max_steps):
            self._record(
                session=session,
                event_type="step_started",
                payload={
                    "step_index": step_index,
                    "reason": (
                        "initial" if step_index == 0 else f"after_{prev_terminal}"
                    ),
                },
            )

            self._maybe_compact(session, trigger="threshold")

            step_input = user_input if step_index == 0 else ""
            decision, decision_started, decision_ended = self._call_model_with_overflow(
                session, step_input
            )
            self._record(
                session=session,
                event_type="model_call",
                payload=self._model_call_payload(
                    decision=decision,
                    started_at=decision_started,
                    ended_at=decision_ended,
                    session=session,
                ),
            )
            self._record(
                session=session,
                event_type="decision_made",
                payload={
                    "kind": decision.kind,
                    "tool_name": decision.tool_name,
                    "tool_args": decision.tool_args,
                    "assistant_message": decision.assistant_message,
                },
            )

            step_response, step_outcome = self._apply_decision(session, decision)
            last_response = step_response
            prev_terminal = step_outcome
            steps_used = step_index + 1
            session.step_count += 1
            session.last_step_at = self._clock.now()

            self._record(
                session=session,
                event_type="step_completed",
                payload={
                    "step_index": step_index,
                    "outcome": step_outcome,
                },
            )

            if decision.kind in TERMINAL_DECISION_KINDS:
                terminal_reason = decision.kind
                break

        self._record(
            session=session,
            event_type="session_finished",
            payload={
                "reason": terminal_reason,
                "steps": steps_used,
            },
        )

        session.turn_count += 1
        if terminal_reason == "final":
            session.status = "done"
        elif terminal_reason == "ask_user":
            session.status = "waiting_user"
        # Hitting max_steps leaves status as "running" — the next
        # run_session call can extend the session.
        self._sessions.save(session)
        return last_response

    # ------------------------------------------------------------------
    # compaction
    # ------------------------------------------------------------------

    def _maybe_compact(self, session: Session, *, trigger: str) -> None:
        """Compact older messages when the conversation exceeds the budget.

        Emits ``compaction_started`` and ``compaction_completed`` trace
        events around the work. The summary is produced by the
        loop-level summarizer when supplied; otherwise the
        deterministic fallback in :mod:`harnesslab.core.compaction`
        is used so eval and replay stay reproducible.
        """

        threshold = self._limits.compaction_threshold_tokens
        if not should_compact(session.messages, threshold_tokens=threshold):
            return
        self._do_compact(
            session,
            trigger=trigger,
            keep_last=self._limits.compaction_keep_last_messages,
        )

    def _do_compact(
        self,
        session: Session,
        *,
        trigger: str,
        keep_last: int,
        estimated_tokens_override: int | None = None,
    ) -> None:
        estimated = (
            estimated_tokens_override
            if estimated_tokens_override is not None
            else estimate_messages_tokens(session.messages)
        )
        self._record(
            session=session,
            event_type="compaction_started",
            payload={
                "trigger": trigger,
                "message_count": len(session.messages),
                "estimated_tokens": estimated,
                "threshold_tokens": self._limits.compaction_threshold_tokens,
                "keep_last": keep_last,
            },
        )

        new_messages, stats = compact_messages(
            session.messages,
            keep_last=keep_last,
            summarizer=self._summarizer,
            now=self._clock.now(),
            new_id=self._ids.new_id,
        )
        session.messages = new_messages

        self._record(
            session=session,
            event_type="compaction_completed",
            payload={
                "trigger": trigger,
                **stats,
                "estimated_tokens_after": estimate_messages_tokens(new_messages),
            },
        )

    def _call_model_with_overflow(
        self,
        session: Session,
        step_input: str,
    ) -> tuple[Decision, datetime, datetime]:
        """Call the model; on overflow, force-compact and retry once.

        Adapters signal overflow by raising
        :class:`ModelOverflowError`. The first retry uses
        ``keep_last=max(1, configured // 2)`` so the next request
        is materially smaller. If the second call also overflows,
        the error propagates as a terminal ``final`` decision so
        the loop ends cleanly with a recognizable message instead
        of crashing the CLI.
        """

        try:
            return self._call_model(session, step_input)
        except ModelOverflowError as overflow:
            emergency_keep_last = max(
                1, self._limits.compaction_keep_last_messages // 2
            )
            self._do_compact(
                session,
                trigger="overflow",
                keep_last=emergency_keep_last,
                estimated_tokens_override=overflow.estimated_tokens,
            )
            try:
                return self._call_model(session, step_input)
            except ModelOverflowError as second:
                started = self._clock.now()
                ended = self._clock.now()
                msg = (
                    "Context window exceeded even after emergency compaction "
                    f"(keep_last={emergency_keep_last}). "
                    f"Reason: {second}"
                )
                return (
                    Decision(kind="final", assistant_message=msg),
                    started,
                    ended,
                )

    # ------------------------------------------------------------------
    # model + decision helpers
    # ------------------------------------------------------------------

    def _call_model(
        self,
        session: Session,
        user_input: str,
    ) -> tuple[Decision, datetime, datetime]:
        started = self._clock.now()
        decision = self._model.decide(session, user_input)
        ended = self._clock.now()
        return decision, started, ended

    def _model_call_payload(
        self,
        decision: Decision,
        started_at: datetime,
        ended_at: datetime,
        session: Session,
    ) -> dict:
        raw_meta = self._model_raw_meta()
        payload: dict = {
            "model_name": type(self._model).__name__,
            "decision_kind": decision.kind,
            "latency_ms": (ended_at - started_at).total_seconds() * 1000.0,
        }
        payload.update(self._model_metadata(raw_meta))

        snapshot = make_conversation_snapshot(session.messages, self._limits)
        snapshot = merge_adapter_breakdown(snapshot, raw_meta)
        payload["context"] = snapshot.model_dump(exclude_none=True)
        return payload

    def _model_raw_meta(self) -> dict | None:
        getter = getattr(self._model, "last_call_meta", None)
        if not callable(getter):
            return None
        raw = getter()
        return raw if isinstance(raw, dict) else None

    @staticmethod
    def _model_metadata(raw: dict | None) -> dict:
        if not raw:
            return {}
        allowed = {
            "model_name",
            "request_tokens",
            "response_tokens",
            "total_tokens",
            "provider",
        }
        return {k: raw[k] for k in allowed if k in raw}

    def _apply_decision(
        self,
        session: Session,
        decision: Decision,
    ) -> tuple[str, str]:
        """Apply one decision; return ``(user_visible_response, outcome)``.

        ``outcome`` is the short string written to the ``step_completed``
        trace event. It is one of ``final | ask_user | assistant | tool |
        tool_invalid_args | tool_denied | tool_error | tool_ok``.
        """

        if decision.kind == "final":
            reply = decision.assistant_message or ""
            session.messages.append(
                self._make_message(role="assistant", content=reply, session=session)
            )
            return reply, "final"

        if decision.kind == "ask_user":
            reply = decision.assistant_message or ""
            session.messages.append(
                self._make_message(role="assistant", content=reply, session=session)
            )
            return reply, "ask_user"

        if decision.kind == "assistant":
            reply = decision.assistant_message or ""
            session.messages.append(
                self._make_message(role="assistant", content=reply, session=session)
            )
            return reply, "assistant"

        return self._apply_tool_decision(session, decision)

    def _apply_tool_decision(
        self,
        session: Session,
        decision: Decision,
    ) -> tuple[str, str]:
        call = self._make_tool_call(
            session_id=session.id,
            name=decision.tool_name or "",
            args=decision.tool_args,
        )

        schema_ok, schema_error = self._tools.validate_args(call)
        if not schema_ok:
            invalid_msg = f"Tool args invalid: {schema_error}"
            session.messages.append(
                self._make_message(
                    role="tool",
                    content=invalid_msg,
                    session=session,
                    tool_call_id=call.id,
                )
            )
            self._record(
                session=session,
                event_type="tool_invalid_args",
                payload={
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "args": call.args,
                    "error": schema_error,
                },
            )
            return invalid_msg, "tool_invalid_args"

        allowed, reason = self._policy.allow_tool(call)
        call.policy_decision = f"{'allow' if allowed else 'deny'}:{reason}"

        if not allowed:
            denied_msg = f"Tool denied by policy: {reason}"
            session.messages.append(
                self._make_message(
                    role="tool",
                    content=denied_msg,
                    session=session,
                    tool_call_id=call.id,
                )
            )
            self._record(
                session=session,
                event_type="tool_denied",
                payload={
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "args": call.args,
                    "policy_decision": call.policy_decision,
                    "reason": reason,
                },
            )
            return denied_msg, "tool_denied"

        call.started_at = self._clock.now()
        result = self._tools.execute(call)
        call.ended_at = self._clock.now()

        tool_message = self._format_tool_message(call=call, result=result)
        session.messages.append(
            self._make_message(
                role="tool",
                content=tool_message,
                session=session,
                tool_call_id=call.id,
            )
        )
        self._record(
            session=session,
            event_type="tool_executed",
            payload=self._tool_executed_payload(call=call, result=result),
        )
        return tool_message, "tool_ok" if result.ok else "tool_error"

    def _tool_executed_payload(self, call: ToolCall, result: ToolResult) -> dict:
        duration_ms: float | None = None
        if call.started_at and call.ended_at:
            duration_ms = (call.ended_at - call.started_at).total_seconds() * 1000.0
        output_preview = result.output[:_TRACE_OUTPUT_PREVIEW_BYTES]
        truncated = len(result.output) > _TRACE_OUTPUT_PREVIEW_BYTES
        return {
            "tool_call_id": call.id,
            "tool": call.name,
            "args": call.args,
            "policy_decision": call.policy_decision,
            "started_at": call.started_at.isoformat() if call.started_at else None,
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
            "duration_ms": duration_ms,
            "ok": result.ok,
            "error": result.error,
            "output_size": len(result.output),
            "output_preview": output_preview,
            "output_truncated": truncated,
        }

    def _make_message(
        self,
        role: str,
        content: str,
        session: Session,
        tool_call_id: str | None = None,
    ) -> Message:
        return Message(
            id=self._ids.new_id("msg"),
            role=role,  # type: ignore[arg-type]
            content=content,
            created_at=self._clock.now(),
            session_id=session.id,
            tool_call_id=tool_call_id,
        )

    def _make_tool_call(self, session_id: str, name: str, args: dict) -> ToolCall:
        return ToolCall(
            id=self._ids.new_id("tool"),
            name=name,
            args=args,
            session_id=session_id,
        )

    def _record(self, session: Session, event_type: str, payload: dict) -> None:
        self._trace.record(
            TraceEvent(
                run_id=session.id,
                session_id=session.id,
                event_type=event_type,
                payload=payload,
                created_at=self._clock.now(),
            )
        )

    @staticmethod
    def _format_tool_message(call: ToolCall, result: ToolResult) -> str:
        if result.ok:
            return f"[tool:{call.name}] {result.output}"
        return f"[tool:{call.name}] failed: {result.error or 'unknown error'}"


_TITLE_MAX_LEN = 60


def _derive_title(text: str) -> str:
    """Turn a goal or user input into a short, single-line label.

    The first non-empty line is used; lines longer than
    :data:`_TITLE_MAX_LEN` are truncated with an ellipsis. Empty input
    yields the placeholder string ``"(no title)"`` so the
    ``session ls`` CLI never has to render ``None``.
    """

    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) <= _TITLE_MAX_LEN:
            return stripped
        return stripped[: _TITLE_MAX_LEN - 1].rstrip() + "…"
    return "(no title)"
