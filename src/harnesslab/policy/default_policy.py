from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Literal

from harnesslab.core.models import ToolCall
from harnesslab.policy.shell_profiles import (
    DEFAULT_SHELL_PROFILE,
    resolve_shell_profile,
)
from harnesslab.tools.fetch_url_tool import (
    DEFAULT_FETCH_HOST_ALLOWLIST,
    DEFAULT_FETCH_MODE,
    parse_csv_hosts,
    validate_fetch_url,
)

SHELL_METACHARS: frozenset[str] = frozenset("&|;<>`$()\n\r")

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
        shell_profile: str | None = None,
        fetch_url_mode: Literal["strict", "open"] = DEFAULT_FETCH_MODE,
        fetch_url_allowlist: frozenset[str] | None = None,
        fetch_url_deny_hosts: frozenset[str] | None = None,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        if shell_allowlist is not None:
            self._shell_allowlist = frozenset(shell_allowlist)
            self._shell_profile = "custom"
        else:
            profile_name = shell_profile or DEFAULT_SHELL_PROFILE
            self._shell_allowlist = resolve_shell_profile(profile_name)
            self._shell_profile = profile_name.strip().lower()
        self._shell_denylist = (
            frozenset(shell_denylist) if shell_denylist is not None else DEFAULT_SHELL_DENYLIST
        )
        self._fetch_url_mode = fetch_url_mode
        self._fetch_url_allowlist = fetch_url_allowlist or DEFAULT_FETCH_HOST_ALLOWLIST
        env_deny_hosts = parse_csv_hosts(os.environ.get("HARNESSLAB_FETCH_URL_DENY_HOSTS"))
        self._fetch_url_deny_hosts = (fetch_url_deny_hosts or frozenset()) | env_deny_hosts

    def allow_tool(self, call: ToolCall) -> tuple[bool, str]:
        if call.name in {"read_file", "write_file", "edit_file", "apply_patch", "read_pdf"}:
            return self._check_path(call)

        if call.name in {"grep", "glob"}:
            return self._check_optional_path(call)

        if call.name in {"web_search", "html_to_markdown"}:
            return True, "ok"

        if call.name == "fetch_url":
            return self._check_fetch_url(call)

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

    def _check_fetch_url(self, call: ToolCall) -> tuple[bool, str]:
        return validate_fetch_url(
            str(call.args.get("url", "")),
            allowlist=self._fetch_url_allowlist,
            deny_hosts=self._fetch_url_deny_hosts,
            mode=self._fetch_url_mode,
        )

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
