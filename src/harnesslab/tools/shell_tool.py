from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from harnesslab.core.models import ToolCall, ToolResult

_MAX_OUTPUT_BYTES = 65536


class RunShellSafeTool:
    def __init__(self, workspace_root: Path, timeout_seconds: int = 5) -> None:
        self._workspace_root = workspace_root
        self._timeout_seconds = timeout_seconds

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
                timeout=self._timeout_seconds,
                check=False,
            )
            merged = (proc.stdout + proc.stderr).strip()
            output = merged[:_MAX_OUTPUT_BYTES] if merged else "(no output)"
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
