from __future__ import annotations

import shlex
from pathlib import Path

from harnesslab.core.models import ToolCall

SHELL_METACHARS: frozenset[str] = frozenset("&|;<>`$()\n\r")

DEFAULT_SHELL_ALLOWLIST: frozenset[str] = frozenset({"ls", "pwd", "echo", "cat"})

DEFAULT_SHELL_DENYLIST: frozenset[str] = frozenset(
    {
        "rm",
        "sudo",
        "curl",
        "wget",
        "dd",
        "mkfs",
        "mount",
        "umount",
        "chmod",
        "chown",
        "kill",
        "killall",
        "shutdown",
        "reboot",
        "scp",
        "ssh",
    }
)


class DefaultPolicy:
    def __init__(
        self,
        workspace_root: Path,
        shell_allowlist: set[str] | frozenset[str] | None = None,
        shell_denylist: set[str] | frozenset[str] | None = None,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._shell_allowlist = (
            frozenset(shell_allowlist) if shell_allowlist is not None else DEFAULT_SHELL_ALLOWLIST
        )
        self._shell_denylist = (
            frozenset(shell_denylist) if shell_denylist is not None else DEFAULT_SHELL_DENYLIST
        )

    def allow_tool(self, call: ToolCall) -> tuple[bool, str]:
        if call.name in {"read_file", "write_file", "edit_file"}:
            return self._check_path(call)

        if call.name in {"grep", "glob"}:
            return self._check_optional_path(call)

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

    def _check_optional_path(self, call: ToolCall) -> tuple[bool, str]:
        """For tools where ``path`` is optional (defaults to workspace root).

        When provided, it must still resolve inside the workspace —
        the same out-of-workspace check applies, just lifted past the
        empty-string case.
        """

        raw_path = str(call.args.get("path", "") or "").strip()
        if not raw_path:
            return True, "ok"
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
        # Denylist is checked before allowlist so that even if a destructive
        # command is mistakenly added to the allowlist, it stays rejected.
        if head in self._shell_denylist:
            return False, f"command '{head}' is on the denylist"
        if head not in self._shell_allowlist:
            return False, f"command '{head}' not in allowlist"
        return True, "ok"
