from __future__ import annotations

import shlex
from pathlib import Path

from harnesslab.core.models import ToolCall

SHELL_METACHARS: frozenset[str] = frozenset("&|;<>`$()\n\r")

# Commands the agent is permitted to invoke through ``run_shell_safe``.
#
# Scope: this allowlist defends against the agent issuing a single
# obviously-destructive command directly. It does NOT promise that
# ``python``/``pytest``/``uv run`` invocations cannot run arbitrary
# code — a malicious or buggy script can. The workspace sandbox
# (``cwd``) and the file tools' path checks remain the primary
# defenses for that. Add commands here only when they are clearly
# read-only or scoped to the workspace.
DEFAULT_SHELL_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Original Phase 1 minimum.
        "ls",
        "pwd",
        "echo",
        "cat",
        # File inspection.
        "head",
        "tail",
        "wc",
        "file",
        "du",
        "df",
        "stat",
        # Discovery / introspection.
        "which",
        "env",
        "date",
        "whoami",
        "hostname",
        "uname",
        # Search and tree (the grep/glob tools cover this too, but
        # models sometimes reach for the shell out of habit).
        "find",
        "tree",
        # Dev tooling (Python-first stack).
        "python",
        "python3",
        "pytest",
        "ruff",
        "mypy",
        "uv",
        # Git is special-cased: only the read-only subcommands in
        # SAFE_GIT_SUBCOMMANDS are accepted; everything else
        # (push/reset/clean/checkout/…) is denied even though the
        # head ``git`` appears here.
        "git",
    }
)

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

# When the head argv is ``git``, the second argv must be in this set.
# Subcommands that mutate history, remotes, or the working tree
# (``push``, ``reset``, ``checkout``, ``clean``, ``rebase``, ``stash``
# write paths, etc.) are intentionally absent so the policy rejects
# them even though ``git`` is in the allowlist.
SAFE_GIT_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "branch",
        "remote",
        "ls-files",
        "ls-tree",
        "rev-parse",
        "describe",
        "tag",
        "blame",
        "shortlog",
        "config",
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
        if head == "git":
            return self._check_git_argv(argv)
        return True, "ok"

    @staticmethod
    def _check_git_argv(argv: list[str]) -> tuple[bool, str]:
        if len(argv) < 2:
            return False, "git requires a subcommand"
        sub = argv[1]
        if sub not in SAFE_GIT_SUBCOMMANDS:
            return (
                False,
                f"git subcommand '{sub}' not allowed "
                f"(safe set: {', '.join(sorted(SAFE_GIT_SUBCOMMANDS))})",
            )
        return True, "ok"
