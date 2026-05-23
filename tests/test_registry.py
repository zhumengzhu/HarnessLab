from typing import Any

from harnesslab.core.models import ToolCall, ToolResult
from harnesslab.tools.registry import ToolRegistry


class _ExplodingTool:
    name = "boom"
    description = "Always raises."
    args_schema: dict[str, Any] = {"type": "object"}

    def execute(self, call: ToolCall) -> ToolResult:
        raise RuntimeError("kaboom")


def test_registry_returns_not_found_for_unknown_tool() -> None:
    registry = ToolRegistry()
    result = registry.execute(ToolCall(name="missing", args={}))
    assert result.ok is False
    assert "not found" in (result.error or "")


def test_registry_catches_tool_exception() -> None:
    registry = ToolRegistry()
    registry.register(_ExplodingTool())
    result = registry.execute(ToolCall(name="boom", args={}))
    assert result.ok is False
    assert result.error is not None
    assert "crashed" in result.error
    assert "kaboom" in result.error
