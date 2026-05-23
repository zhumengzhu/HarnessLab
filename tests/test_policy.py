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
    # ``arbitrary-binary`` is not in the default allowlist nor the denylist;
    # the policy must still refuse it because the allowlist is exhaustive.
    call = ToolCall(name="run_shell_safe", args={"command": "arbitrary-binary"})
    allowed, reason = policy.allow_tool(call)
    assert allowed is False
    assert "not in allowlist" in reason


def test_unknown_tool_is_denied_by_default(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    call = ToolCall(name="rm_rf", args={})
    allowed, reason = policy.allow_tool(call)
    assert allowed is False
    assert "unknown tool" in reason


def test_shell_denylist_blocks_default_destructive_commands(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    for cmd in ("rm -rf .", "sudo ls", "curl http://example.com"):
        call = ToolCall(name="run_shell_safe", args={"command": cmd})
        allowed, reason = policy.allow_tool(call)
        assert allowed is False, cmd
        assert "denylist" in reason, cmd


def test_shell_denylist_overrides_allowlist(tmp_path: Path) -> None:
    # Even when 'rm' is mistakenly placed in the allowlist, the denylist wins.
    policy = DefaultPolicy(
        workspace_root=tmp_path,
        shell_allowlist={"rm", "ls"},
    )
    call = ToolCall(name="run_shell_safe", args={"command": "rm -rf ."})
    allowed, reason = policy.allow_tool(call)
    assert allowed is False
    assert "denylist" in reason


def test_shell_allowlist_admits_common_read_only_dev_commands(tmp_path: Path) -> None:
    """The expanded Phase 2.5 allowlist must accept the everyday read-only set."""

    policy = DefaultPolicy(workspace_root=tmp_path)
    for cmd in (
        "head README.md",
        "tail -n 20 src/file.py",
        "wc -l src/file.py",
        "which python3",
        "uname -a",
        "find . -name notes.md",
        "python --version",
        "pytest -q",
        "ruff check",
        "uv run pytest -q",
    ):
        allowed, reason = policy.allow_tool(
            ToolCall(name="run_shell_safe", args={"command": cmd})
        )
        assert allowed, f"{cmd}: {reason}"


def test_git_subcommand_allowlist_admits_read_only_subcommands(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    for cmd in (
        "git status",
        "git log --oneline -n 5",
        "git diff HEAD~1 HEAD",
        "git show HEAD",
        "git branch -a",
        "git remote -v",
        "git rev-parse HEAD",
    ):
        allowed, reason = policy.allow_tool(
            ToolCall(name="run_shell_safe", args={"command": cmd})
        )
        assert allowed, f"{cmd}: {reason}"


def test_git_subcommand_allowlist_blocks_destructive_subcommands(
    tmp_path: Path,
) -> None:
    """``git`` is in the head allowlist, but only read-only subcommands pass."""

    policy = DefaultPolicy(workspace_root=tmp_path)
    for cmd in (
        "git push origin main",
        "git reset --hard HEAD",
        "git checkout main",
        "git clean -fdx",
        "git rebase main",
        "git stash",
        "git merge feature",
        "git commit -m hi",
        "git fetch",
        "git pull",
    ):
        allowed, reason = policy.allow_tool(
            ToolCall(name="run_shell_safe", args={"command": cmd})
        )
        assert allowed is False, cmd
        assert "git subcommand" in reason, cmd


def test_bare_git_requires_a_subcommand(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, reason = policy.allow_tool(
        ToolCall(name="run_shell_safe", args={"command": "git"})
    )
    assert allowed is False
    assert "requires a subcommand" in reason


def test_shell_denylist_can_be_customized(tmp_path: Path) -> None:
    # Empty denylist + allowlist containing 'rm' would let 'rm' through;
    # this proves denylist is the source of the rejection above, not the
    # absence from allowlist.
    policy = DefaultPolicy(
        workspace_root=tmp_path,
        shell_allowlist={"rm"},
        shell_denylist=set(),
    )
    call = ToolCall(name="run_shell_safe", args={"command": "rm /tmp/nope"})
    allowed, reason = policy.allow_tool(call)
    assert allowed is True
    assert reason == "ok"
