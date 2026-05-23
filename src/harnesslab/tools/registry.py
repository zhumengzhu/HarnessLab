from __future__ import annotations

import jsonschema

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

    def validate_args(self, call: ToolCall) -> tuple[bool, str | None]:
        """Validate ``call.args`` against the registered tool's args_schema.

        Returns ``(True, None)`` when the tool is unknown or has no schema:
        unknown tools are intentionally deferred to the policy layer so the
        "unknown tool" responsibility lives in exactly one place.
        """

        tool = self._tools.get(call.name)
        if tool is None:
            return True, None
        schema = getattr(tool, "args_schema", None)
        if not schema:
            return True, None
        try:
            jsonschema.validate(instance=call.args, schema=schema)
        except jsonschema.ValidationError as exc:
            return False, exc.message
        except jsonschema.SchemaError as exc:
            return False, f"invalid args_schema for tool '{call.name}': {exc.message}"
        return True, None

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
