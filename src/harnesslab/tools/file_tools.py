from __future__ import annotations

from pathlib import Path

from harnesslab.core.models import ToolCall, ToolResult


class ReadFileTool:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = (self._workspace_root / str(call.args["path"])).resolve()
            content = path.read_text(encoding="utf-8")
            return ToolResult(ok=True, output=content[:65536])
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class WriteFileTool:
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
