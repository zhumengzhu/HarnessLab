"""Isolated Python execution tool (Phase 5.5)."""

from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import ToolCall, ToolResult

DEFAULT_PYTHON_SANDBOX_TIMEOUT = 10


class RunPythonSandboxedTool:
    name = "run_python_sandboxed"
    description = (
        "Execute Python code in an isolated subprocess (python -I -S) with "
        "bounded stdout. Working directory is a fresh temp dir per call."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source to execute."},
            "stdin": {"type": "string", "description": "Optional stdin text."},
        },
        "required": ["code"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        workspace_root: Path,
        limits: RuntimeLimits | None = None,
        *,
        timeout_seconds: int = DEFAULT_PYTHON_SANDBOX_TIMEOUT,
    ) -> None:
        self._workspace_root = workspace_root
        self._limits = limits or RuntimeLimits()
        self._timeout = timeout_seconds

    def execute(self, call: ToolCall) -> ToolResult:
        code = str(call.args.get("code", ""))
        if not code.strip():
            return ToolResult(ok=False, output="", error="code is required")
        stdin_text = str(call.args.get("stdin", ""))

        with tempfile.TemporaryDirectory(prefix="hl-sandbox-") as tmp:
            tmp_path = Path(tmp)
            script = tmp_path / "main.py"
            script.write_text(code, encoding="utf-8")
            argv = [sys.executable, "-I", "-S", str(script)]
            try:
                proc = subprocess.run(
                    argv,
                    cwd=tmp_path,
                    input=stdin_text or None,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return ToolResult(ok=False, output="", error="sandbox timed out")
            except Exception as exc:  # noqa: BLE001
                return ToolResult(ok=False, output="", error=str(exc))

            merged = (proc.stdout + proc.stderr).strip()
            cap = self._limits.output_bytes_cap
            output = merged[:cap] if merged else "(no output)"
            platform_note = ""
            if platform.system() != "Linux":
                platform_note = " [macOS: no network namespace isolation]"
            if proc.returncode != 0:
                return ToolResult(
                    ok=False,
                    output=output + platform_note,
                    error=f"exit code {proc.returncode}",
                )
            return ToolResult(ok=True, output=output + platform_note)
