"""Tests for runtime resource limits (output cap + shell timeout)."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import ToolCall
from harnesslab.tools.file_tools import ReadFileTool
from harnesslab.tools.shell_tool import RunShellSafeTool


def test_read_file_respects_output_bytes_cap(tmp_path: Path) -> None:
    big = "x" * 200
    (tmp_path / "big.txt").write_text(big, encoding="utf-8")

    tool = ReadFileTool(tmp_path, limits=RuntimeLimits(output_bytes_cap=32))
    result = tool.execute(ToolCall(name="read_file", args={"path": "big.txt"}))

    assert result.ok is True
    assert len(result.output) == 32
    assert result.output == "x" * 32


def test_run_shell_safe_respects_output_bytes_cap(tmp_path: Path) -> None:
    payload = "hello" * 200  # > 64 bytes
    tool = RunShellSafeTool(
        tmp_path,
        limits=RuntimeLimits(output_bytes_cap=16, shell_timeout_seconds=5),
    )
    result = tool.execute(ToolCall(name="run_shell_safe", args={"command": f"echo {payload}"}))

    assert result.ok is True
    assert len(result.output) == 16


def test_run_shell_safe_respects_shell_timeout(tmp_path: Path) -> None:
    tool = RunShellSafeTool(
        tmp_path,
        limits=RuntimeLimits(shell_timeout_seconds=1),
    )
    result = tool.execute(
        ToolCall(name="run_shell_safe", args={"command": "sleep 3"}),
    )
    assert result.ok is False
    assert result.error is not None
    assert "timed out" in result.error


def test_runtime_limits_defaults() -> None:
    limits = RuntimeLimits()
    assert limits.output_bytes_cap == 65536
    assert limits.shell_timeout_seconds == 5
