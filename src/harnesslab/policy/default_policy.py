from __future__ import annotations

import shlex
from pathlib import Path

from harnesslab.core.models import ToolCall

SHELL_METACHARS: frozenset[str] = frozenset("&|;<>`$()\n\r")


class DefaultPolicy:
    def __init__(self, workspace_root: Path, shell_allowlist: set[str] | None = None) -> None:
        self._workspace_root = workspace_root.resolve()
        self._shell_allowlist = shell_allowlist or {"ls", "pwd", "echo", "cat"}

    def allow_tool(self, call: ToolCall) -> tuple[bool, str]:
        if call.name in {"read_file", "write_file"}:
            return self._check_path(call)

        if call.name == "run_shell_safe":
            return self._check_shell(call)

        return False, f"unknown tool '{call.name}'"

    def _check_path(self, call: ToolCall) -> tuple[bool, str]:
        raw_path = str(call.args.get("path", ""))
        if not raw_path:
            return False, "missing file path"
        candidate = (self._workspace_root / raw_path).resolve()
        try:
            candidate.relative_to(self._workspace_root)
        except ValueError:
            return False, "path out of workspace"
        return True, "ok"

    def _check_shell(self, call: ToolCall) -> tuple[bool, str]:
        command = str(call.args.get("command", "")).strip()
        if not command:
            return False, "missing command"
        bad = next((c for c in command if c in SHELL_METACHARS), None)
        if bad is not None:
            return False, f"shell metacharacter '{bad}' not allowed"
        try:
            argv = shlex.split(command, posix=True)
        except ValueError as exc:
            return False, f"invalid command: {exc}"
        if not argv:
            return False, "empty command after parsing"
        head = argv[0]
        if head not in self._shell_allowlist:
            return False, f"command '{head}' not in allowlist"
        return True, "ok"
