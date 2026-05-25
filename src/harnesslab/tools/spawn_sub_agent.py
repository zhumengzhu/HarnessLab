"""Supervisor sub-agent spawn tool (Phase 6 PoC)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from harnesslab.core.models import ToolCall, ToolResult


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
        self._spawn_counts[parent_id] = count + 1

        child = loop.start_child(goal=goal, parent_session_id=parent_id)
        final = loop.run_session(child.id, goal, max_steps=max_steps)
        payload = {
            "child_session_id": child.id,
            "parent_session_id": parent_id,
            "final_response": final,
        }
        return ToolResult(ok=True, output=json.dumps(payload, ensure_ascii=False))
