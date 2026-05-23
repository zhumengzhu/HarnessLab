from __future__ import annotations

from harnesslab.core.contracts import (
    ClockPort,
    IdPort,
    ModelPort,
    PolicyPort,
    SessionStorePort,
    TraceRecorderPort,
)
from harnesslab.core.models import Decision, Message, Session, ToolCall, ToolResult, TraceEvent
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.tools.registry import ToolRegistry

_TRACE_OUTPUT_PREVIEW_BYTES = 512


class HarnessLoop:
    def __init__(
        self,
        model: ModelPort,
        policy: PolicyPort,
        sessions: SessionStorePort,
        tools: ToolRegistry,
        trace: TraceRecorderPort,
        clock: ClockPort | None = None,
        ids: IdPort | None = None,
    ) -> None:
        self._model = model
        self._policy = policy
        self._sessions = sessions
        self._tools = tools
        self._trace = trace
        self._clock: ClockPort = clock or SystemClock()
        self._ids: IdPort = ids or UuidIdProvider()

    def start(self, goal: str) -> Session:
        session = Session(
            id=self._ids.new_id("ses"),
            goal=goal,
            created_at=self._clock.now(),
        )
        self._sessions.create(session)
        self._record(
            session=session,
            event_type="session_started",
            payload={"goal": goal},
        )
        return session

    def run_turn(self, session_id: str, user_input: str) -> str:
        session = self._sessions.get(session_id)
        session.messages.append(
            self._make_message(role="user", content=user_input, session=session)
        )
        decision = self._model.decide(session, user_input)
        self._record(
            session=session,
            event_type="decision_made",
            payload={"kind": decision.kind, "tool_name": decision.tool_name},
        )
        response = self._apply_decision(session, decision)
        session.turn_count += 1
        self._sessions.save(session)
        return response

    def _apply_decision(self, session: Session, decision: Decision) -> str:
        if decision.kind == "assistant":
            reply = decision.assistant_message or "No response."
            session.messages.append(
                self._make_message(role="assistant", content=reply, session=session)
            )
            return reply

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
            return invalid_msg

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
            return denied_msg

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
        return tool_message

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
