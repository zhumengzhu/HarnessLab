from __future__ import annotations

from pathlib import Path
from typing import Any

from harnesslab.core.models import ToolCall, ToolResult

_MAX_OUTPUT_BYTES = 65536


class ReadFileTool:
    name = "read_file"
    description = "Read a UTF-8 text file from inside the workspace."
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative file path."},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = (self._workspace_root / str(call.args["path"])).resolve()
            content = path.read_text(encoding="utf-8")
            return ToolResult(ok=True, output=content[:_MAX_OUTPUT_BYTES])
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class WriteFileTool:
    name = "write_file"
    description = "Write a UTF-8 text file inside the workspace (creates parents)."
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative file path."},
            "content": {"type": "string", "description": "Text content to write."},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = (self._workspace_root / str(call.args["path"])).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(call.args.get("content", "")), encoding="utf-8")
            return ToolResult(ok=True, output=f"wrote {path}")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))
