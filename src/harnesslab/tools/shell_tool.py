from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import ToolCall, ToolResult


class RunShellSafeTool:
    name = "run_shell_safe"
    description = (
        "Run a whitelisted command without shell interpretation. "
        "Command must be a single argv expressible string (no &&, ||, |, ;, <, >, `, $())."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command line; parsed via shlex and executed with shell=False.",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        workspace_root: Path,
        limits: RuntimeLimits | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._limits = limits or RuntimeLimits()

    def execute(self, call: ToolCall) -> ToolResult:
        command = str(call.args.get("command", "")).strip()
        if not command:
            return ToolResult(ok=False, output="", error="command is required")

        try:
            argv = shlex.split(command, posix=True)
        except ValueError as exc:
            return ToolResult(ok=False, output="", error=f"invalid command: {exc}")
        if not argv:
            return ToolResult(ok=False, output="", error="empty command after parsing")

        try:
            proc = subprocess.run(
                argv,
                cwd=self._workspace_root,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._limits.shell_timeout_seconds,
                check=False,
            )
            merged = (proc.stdout + proc.stderr).strip()
            output = (
                merged[: self._limits.output_bytes_cap] if merged else "(no output)"
            )
            if proc.returncode != 0:
                return ToolResult(
                    ok=False,
                    output=output,
                    error=f"exit code {proc.returncode}",
                )
            return ToolResult(ok=True, output=output)
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, output="", error="command timed out")
        except FileNotFoundError as exc:
            return ToolResult(ok=False, output="", error=f"executable not found: {exc}")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))
