from __future__ import annotations

from harnesslab.core.contracts import ToolPort
from harnesslab.core.models import ToolCall, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolPort] = {}

    def register(self, tool: ToolPort, name: str | None = None) -> None:
        key = name or tool.name
        self._tools[key] = tool

    def get(self, name: str) -> ToolPort | None:
        return self._tools.get(name)

    def list(self) -> list[ToolPort]:
        return list(self._tools.values())

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(ok=False, output="", error=f"tool '{call.name}' not found")
        try:
            return tool.execute(call)
        except Exception as exc:
            return ToolResult(
                ok=False,
                output="",
                error=f"crashed: {type(exc).__name__}: {exc}",
            )
