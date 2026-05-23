from __future__ import annotations

from harnesslab.core.models import ToolCall, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, object] = {}

    def register(self, tool: object, name: str) -> None:
        self._tools[name] = tool

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(ok=False, output="", error=f"tool '{call.name}' not found")
        return tool.execute(call)
