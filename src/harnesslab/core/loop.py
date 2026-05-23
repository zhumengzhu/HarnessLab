from __future__ import annotations

from harnesslab.core.contracts import (
    ModelPort,
    PolicyPort,
    SessionStorePort,
    TraceRecorderPort,
)
from harnesslab.core.models import Decision, Message, Session, ToolCall, ToolResult, TraceEvent
from harnesslab.tools.registry import ToolRegistry


class HarnessLoop:
    def __init__(
        self,
        model: ModelPort,
        policy: PolicyPort,
        sessions: SessionStorePort,
        tools: ToolRegistry,
        trace: TraceRecorderPort,
    ) -> None:
        self._model = model
        self._policy = policy
        self._sessions = sessions
        self._tools = tools
        self._trace = trace

    def start(self, goal: str) -> Session:
        session = self._sessions.create(goal=goal)
        self._trace.record(
            TraceEvent(
                run_id=session.id,
                session_id=session.id,
                event_type="session_started",
                payload={"goal": goal},
            )
        )
        return session

    def run_turn(self, session_id: str, user_input: str) -> str:
        session = self._sessions.get(session_id)
        session.messages.append(Message(role="user", content=user_input))
        decision = self._model.decide(session, user_input)
        self._trace.record(
            TraceEvent(
                run_id=session.id,
                session_id=session.id,
                event_type="decision_made",
                payload=decision.model_dump(),
            )
        )

        response = self._apply_decision(session, decision)
        session.turn_count += 1
        self._sessions.save(session)
        return response

    def _apply_decision(self, session: Session, decision: Decision) -> str:
        if decision.kind == "assistant":
            reply = decision.assistant_message or "No response."
            session.messages.append(Message(role="assistant", content=reply))
            return reply

        call = ToolCall(name=decision.tool_name or "", args=decision.tool_args)
        allowed, reason = self._policy.allow_tool(call)
        if not allowed:
            denied_msg = f"Tool denied by policy: {reason}"
            session.messages.append(Message(role="assistant", content=denied_msg))
            self._trace.record(
                TraceEvent(
                    run_id=session.id,
                    session_id=session.id,
                    event_type="tool_denied",
                    payload={"tool": call.name, "reason": reason},
                )
            )
            return denied_msg

        result = self._tools.execute(call)
        self._trace.record(
            TraceEvent(
                run_id=session.id,
                session_id=session.id,
                event_type="tool_executed",
                payload={"tool": call.name, "ok": result.ok},
            )
        )
        tool_message = self._format_tool_message(call=call, result=result)
        session.messages.append(Message(role="tool", content=tool_message))
        session.messages.append(Message(role="assistant", content=tool_message))
        return tool_message

    @staticmethod
    def _format_tool_message(call: ToolCall, result: ToolResult) -> str:
        if result.ok:
            return f"[tool:{call.name}] {result.output}"
        return f"[tool:{call.name}] failed: {result.error or 'unknown error'}"
