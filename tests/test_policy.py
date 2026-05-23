from pathlib import Path

from harnesslab.core.models import ToolCall
from harnesslab.policy.default_policy import DefaultPolicy


def test_path_prefix_lookalike_is_denied(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sibling = tmp_path / "ws_evil"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("nope", encoding="utf-8")

    policy = DefaultPolicy(workspace_root=workspace)
    call = ToolCall(name="read_file", args={"path": "../ws_evil/secret.txt"})

    allowed, reason = policy.allow_tool(call)
    assert allowed is False
    assert "out of workspace" in reason


def test_path_inside_workspace_is_allowed(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    call = ToolCall(name="read_file", args={"path": "notes/a.txt"})
    allowed, reason = policy.allow_tool(call)
    assert allowed is True
    assert reason == "ok"


def test_shell_metachar_is_denied(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    call = ToolCall(name="run_shell_safe", args={"command": "ls && echo pwned"})
    allowed, reason = policy.allow_tool(call)
    assert allowed is False
    assert "metacharacter" in reason


def test_shell_unknown_command_is_denied(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    call = ToolCall(name="run_shell_safe", args={"command": "whoami"})
    allowed, reason = policy.allow_tool(call)
    assert allowed is False
    assert "not in allowlist" in reason


def test_unknown_tool_is_denied_by_default(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    call = ToolCall(name="rm_rf", args={})
    allowed, reason = policy.allow_tool(call)
    assert allowed is False
    assert "unknown tool" in reason
