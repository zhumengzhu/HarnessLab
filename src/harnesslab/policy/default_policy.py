from __future__ import annotations

from pathlib import Path

from harnesslab.core.models import ToolCall


class DefaultPolicy:
    def __init__(self, workspace_root: Path, shell_allowlist: set[str] | None = None) -> None:
        self._workspace_root = workspace_root.resolve()
        self._shell_allowlist = shell_allowlist or {"ls", "pwd", "echo"}

    def allow_tool(self, call: ToolCall) -> tuple[bool, str]:
        if call.name in {"read_file", "write_file"}:
            raw_path = str(call.args.get("path", ""))
            if not raw_path:
                return False, "missing file path"
            path = (self._workspace_root / raw_path).resolve()
            if not str(path).startswith(str(self._workspace_root)):
                return False, "path out of workspace"
            return True, "ok"

        if call.name == "run_shell_safe":
            command = str(call.args.get("command", "")).strip()
            first = command.split(" ", maxsplit=1)[0] if command else ""
            if first not in self._shell_allowlist:
                return False, f"command '{first}' not in allowlist"
            return True, "ok"

        return False, f"unknown tool '{call.name}'"
