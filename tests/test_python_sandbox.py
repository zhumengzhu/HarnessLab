"""Tests for python sandbox tool (Phase 5.5)."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.models import ToolCall
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.tools.python_sandbox_tool import RunPythonSandboxedTool


def test_python_sandbox_compute(tmp_path: Path) -> None:
    tool = RunPythonSandboxedTool(tmp_path)
    policy = DefaultPolicy(tmp_path, python_sandbox_profile="local")
    call = ToolCall(name="run_python_sandboxed", args={"code": "print(2 + 2)"})
    allowed, _ = policy.allow_tool(call)
    assert allowed
    result = tool.execute(call)
    assert result.ok is True
    assert "4" in result.output


def test_python_sandbox_disabled_by_default(tmp_path: Path) -> None:
    policy = DefaultPolicy(tmp_path)
    call = ToolCall(name="run_python_sandboxed", args={"code": "print(1)"})
    allowed, reason = policy.allow_tool(call)
    assert allowed is False
    assert "disabled" in reason
