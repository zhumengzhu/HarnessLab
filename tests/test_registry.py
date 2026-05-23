from typing import Any

from harnesslab.core.models import ToolCall, ToolResult
from harnesslab.tools.registry import ToolRegistry


class _ExplodingTool:
    name = "boom"
    description = "Always raises."
    args_schema: dict[str, Any] = {"type": "object"}

    def execute(self, call: ToolCall) -> ToolResult:
        raise RuntimeError("kaboom")


class _SchemaTool:
    name = "schema_tool"
    description = "Tool with a strict schema for testing validate_args."
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "minimum": 0},
        },
        "required": ["x"],
        "additionalProperties": False,
    }

    def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(ok=True, output=f"x={call.args['x']}")


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


def test_validate_args_passes_for_valid_payload() -> None:
    registry = ToolRegistry()
    registry.register(_SchemaTool())
    ok, error = registry.validate_args(ToolCall(name="schema_tool", args={"x": 1}))
    assert ok is True
    assert error is None


def test_validate_args_rejects_missing_required_field() -> None:
    registry = ToolRegistry()
    registry.register(_SchemaTool())
    ok, error = registry.validate_args(ToolCall(name="schema_tool", args={}))
    assert ok is False
    assert error is not None
    assert "'x'" in error


def test_validate_args_rejects_extra_property() -> None:
    registry = ToolRegistry()
    registry.register(_SchemaTool())
    ok, error = registry.validate_args(
        ToolCall(name="schema_tool", args={"x": 1, "y": 2}),
    )
    assert ok is False
    assert error is not None


def test_validate_args_rejects_wrong_type() -> None:
    registry = ToolRegistry()
    registry.register(_SchemaTool())
    ok, error = registry.validate_args(
        ToolCall(name="schema_tool", args={"x": "not-an-int"}),
    )
    assert ok is False
    assert error is not None


def test_validate_args_defers_unknown_tool_to_policy() -> None:
    registry = ToolRegistry()
    ok, error = registry.validate_args(ToolCall(name="missing", args={"x": 1}))
    assert ok is True
    assert error is None
