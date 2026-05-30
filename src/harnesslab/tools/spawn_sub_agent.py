"""Supervisor sub-agent spawn tool (Phase 6 PoC)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from harnesslab.core.models import ToolCall, ToolResult


def _parent_chain_depth(loop: Any, session_id: str) -> int:
    """Count ancestors via ``parent_session_id`` (root session → 0)."""

    depth = 0
    current_id = session_id
    seen: set[str] = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        session = loop._sessions.get(current_id)
        parent_id = getattr(session, "parent_session_id", None)
        if not parent_id:
            break
        depth += 1
        current_id = parent_id
    return depth


class SpawnSubAgentTool:
    name = "spawn_sub_agent"
    description = (
        "Run a child agent session to completion and return its final response. "
        "Child sessions inherit parent_session_id for trace lineage."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Child session goal."},
            "max_steps": {
                "type": "integer",
                "description": "Inner-loop step budget for the child.",
                "minimum": 1,
            },
        },
        "required": ["goal"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        loop_provider: Callable[[], Any],
        *,
        max_depth: int = 1,
        max_per_session: int = 4,
    ) -> None:
        self._loop_provider = loop_provider
        self._max_depth = max(1, max_depth)
        self._max_per_session = max(1, max_per_session)
        self._spawn_counts: dict[str, int] = {}

    def execute(self, call: ToolCall) -> ToolResult:
        goal = str(call.args.get("goal", "")).strip()
        if not goal:
            return ToolResult(ok=False, output="", error="goal is required")
        max_steps_raw = call.args.get("max_steps", 5)
        try:
            max_steps = max(1, int(max_steps_raw))
        except (TypeError, ValueError):
            max_steps = 5

        loop = self._loop_provider()
        parent_id = getattr(call, "session_id", None)
        if not parent_id:
            return ToolResult(ok=False, output="", error="missing session context")

        count = self._spawn_counts.get(parent_id, 0)
        if count >= self._max_per_session:
            return ToolResult(
                ok=False,
                output="",
                error=f"max sub-agents per session ({self._max_per_session}) exceeded",
            )

        depth = _parent_chain_depth(loop, parent_id)
        if depth >= self._max_depth:
            return ToolResult(
                ok=False,
                output="",
                error=f"max sub-agent depth ({self._max_depth}) exceeded",
            )

        self._spawn_counts[parent_id] = count + 1

        parent_session = loop._sessions.get(parent_id)  # noqa: SLF001
        tool_parent = loop._loop_spans.active_tool  # noqa: SLF001
        if tool_parent is None:
            return ToolResult(
                ok=False,
                output="",
                error="spawn_sub_agent requires active tool span",
            )

        child = loop.start_child(goal=goal, parent_session_id=parent_id)
        run_started = loop._clock.now()  # noqa: SLF001
        with loop._loop_spans.sub_agent_run(  # noqa: SLF001
            parent_session,
            parent_tool=tool_parent,
            goal=goal,
            max_steps=max_steps,
        ) as sub_run:
            final = loop.run_session(child.id, goal, max_steps=max_steps)
            child_session = loop._sessions.get(child.id)  # noqa: SLF001
            child_root = loop._loop_spans.consume_child_turn_root()  # noqa: SLF001
            if child_root is not None:
                loop._loop_spans.link_sub_agent(  # noqa: SLF001
                    sub_run,
                    child_turn_root=child_root,
                    child_session_id=child.id,
                )
            duration_ms = max(
                0.0,
                (loop._clock.now() - run_started).total_seconds() * 1000.0,  # noqa: SLF001
            )
            loop._loop_spans.finish_sub_agent_run(  # noqa: SLF001
                sub_run,
                child_session_id=child.id,
                ok=True,
                metrics={
                    "duration_ms": duration_ms,
                    "step_count": child_session.step_count,
                    "llm_calls_total": child_session.budget_usage.llm_calls_total,
                    "tool_calls_total": child_session.budget_usage.tool_calls_total,
                    "tokens_total": child_session.budget_usage.tokens_total,
                    "cost_usd_total": child_session.budget_usage.cost_usd_total,
                },
            )
        payload = {
            "child_session_id": child.id,
            "parent_session_id": parent_id,
            "final_response": final,
        }
        return ToolResult(ok=True, output=json.dumps(payload, ensure_ascii=False))
