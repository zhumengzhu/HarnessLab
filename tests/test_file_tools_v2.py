"""Tests for Phase 2.5 commit 1: edit_file, grep, glob."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.models import ToolCall
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.tools.file_tools import EditFileTool, GlobTool, GrepTool

# ---------- edit_file ----------


def test_edit_file_replaces_unique_occurrence(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("hello world\nbye world\n", encoding="utf-8")
    tool = EditFileTool(tmp_path)
    result = tool.execute(
        ToolCall(
            name="edit_file",
            args={"path": "a.py", "old": "hello", "new": "hi"},
        )
    )
    assert result.ok
    assert "edited" in result.output
    assert target.read_text(encoding="utf-8") == "hi world\nbye world\n"


def test_edit_file_refuses_when_old_missing(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("nothing here", encoding="utf-8")
    tool = EditFileTool(tmp_path)
    result = tool.execute(
        ToolCall(name="edit_file", args={"path": "a.txt", "old": "missing", "new": "x"})
    )
    assert not result.ok
    assert "not found" in (result.error or "")


def test_edit_file_refuses_when_old_not_unique(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("aa aa aa", encoding="utf-8")
    tool = EditFileTool(tmp_path)
    result = tool.execute(
        ToolCall(name="edit_file", args={"path": "a.txt", "old": "aa", "new": "bb"})
    )
    assert not result.ok
    assert "not unique" in (result.error or "")
    # File untouched.
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "aa aa aa"


def test_edit_file_replace_all_rewrites_every_match(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("aa aa aa", encoding="utf-8")
    tool = EditFileTool(tmp_path)
    result = tool.execute(
        ToolCall(
            name="edit_file",
            args={"path": "a.txt", "old": "aa", "new": "bb", "replace_all": True},
        )
    )
    assert result.ok
    assert "3 replacements" in result.output
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "bb bb bb"


def test_edit_file_refuses_empty_old(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    tool = EditFileTool(tmp_path)
    result = tool.execute(
        ToolCall(name="edit_file", args={"path": "a.txt", "old": "", "new": "x"})
    )
    assert not result.ok
    assert "must not be empty" in (result.error or "")


def test_edit_file_reports_missing_file(tmp_path: Path) -> None:
    tool = EditFileTool(tmp_path)
    result = tool.execute(
        ToolCall(name="edit_file", args={"path": "ghost.txt", "old": "a", "new": "b"})
    )
    assert not result.ok
    assert "file not found" in (result.error or "")


# ---------- grep ----------


def _seed_grep_tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text(
        "def alpha():\n    return 'aa'\n\nclass Beta:\n    pass\n",
        encoding="utf-8",
    )
    (root / "src" / "b.py").write_text(
        "alpha = 1\n# alpha is special\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Project\nNo alpha here\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("alpha-git-noise", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "x.js").write_text("alpha-js-noise", encoding="utf-8")


def test_grep_returns_matches_in_workspace_files(tmp_path: Path) -> None:
    _seed_grep_tree(tmp_path)
    tool = GrepTool(tmp_path)
    result = tool.execute(ToolCall(name="grep", args={"pattern": r"\balpha\b"}))
    assert result.ok
    # Must include matches from src/ and README.md but NOT from .git or node_modules.
    assert "src/a.py:1: def alpha():" in result.output
    assert "src/b.py:1: alpha = 1" in result.output
    assert "README.md:2: No alpha here" in result.output
    assert ".git/config" not in result.output
    assert "node_modules" not in result.output


def test_grep_glob_filter_narrows_files(tmp_path: Path) -> None:
    _seed_grep_tree(tmp_path)
    tool = GrepTool(tmp_path)
    result = tool.execute(
        ToolCall(name="grep", args={"pattern": "alpha", "glob": "*.py"})
    )
    assert result.ok
    assert "src/a.py:" in result.output
    assert "src/b.py:" in result.output
    assert "README.md" not in result.output


def test_grep_invalid_regex_returns_error(tmp_path: Path) -> None:
    tool = GrepTool(tmp_path)
    result = tool.execute(ToolCall(name="grep", args={"pattern": "[unterminated"}))
    assert not result.ok
    assert "invalid regex" in (result.error or "")


def test_grep_no_matches_returns_ok_with_placeholder(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("nothing here\n", encoding="utf-8")
    tool = GrepTool(tmp_path)
    result = tool.execute(ToolCall(name="grep", args={"pattern": "xyz123"}))
    assert result.ok
    assert "(no matches)" in result.output


def test_grep_respects_max_matches(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("hit\n" * 200, encoding="utf-8")
    tool = GrepTool(tmp_path)
    result = tool.execute(
        ToolCall(name="grep", args={"pattern": "hit", "max_matches": 5})
    )
    assert result.ok
    lines = [line for line in result.output.splitlines() if line.startswith("big.txt:")]
    assert len(lines) == 5
    assert "truncated" in result.output


def test_grep_skips_binary_files_without_failing(tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"\x00\xff\x00\xff\x00")
    (tmp_path / "good.txt").write_text("alpha\n", encoding="utf-8")
    tool = GrepTool(tmp_path)
    result = tool.execute(ToolCall(name="grep", args={"pattern": "alpha"}))
    assert result.ok
    assert "good.txt:1: alpha" in result.output


# ---------- glob ----------


def _seed_glob_tree(root: Path) -> None:
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "a.py").write_text("a", encoding="utf-8")
    (root / "src" / "pkg" / "b.py").write_text("b", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("t", encoding="utf-8")
    (root / "README.md").write_text("r", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv" / "noise.py").write_text("n", encoding="utf-8")


def test_glob_returns_relative_paths_sorted(tmp_path: Path) -> None:
    _seed_glob_tree(tmp_path)
    tool = GlobTool(tmp_path)
    result = tool.execute(ToolCall(name="glob", args={"pattern": "**/*.py"}))
    assert result.ok
    lines = result.output.splitlines()
    assert lines == sorted(lines)
    assert "src/pkg/a.py" in lines
    assert "src/pkg/b.py" in lines
    assert "tests/test_a.py" in lines
    # noise dirs filtered out
    assert all(".venv" not in line for line in lines)


def test_glob_returns_placeholder_when_empty(tmp_path: Path) -> None:
    tool = GlobTool(tmp_path)
    result = tool.execute(ToolCall(name="glob", args={"pattern": "*.nope"}))
    assert result.ok
    assert "(no matches)" in result.output


def test_glob_rejects_empty_pattern(tmp_path: Path) -> None:
    tool = GlobTool(tmp_path)
    result = tool.execute(ToolCall(name="glob", args={"pattern": ""}))
    assert not result.ok
    assert "pattern is required" in (result.error or "")


def test_glob_respects_max_results(tmp_path: Path) -> None:
    for i in range(20):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
    tool = GlobTool(tmp_path)
    result = tool.execute(
        ToolCall(name="glob", args={"pattern": "f*.txt", "max_results": 5})
    )
    assert result.ok
    body, *_ = result.output.split("\n(truncated")
    assert len(body.splitlines()) == 5
    assert "truncated" in result.output


# ---------- policy gating for the new tools ----------


def test_policy_admits_edit_file_when_path_is_inside_workspace(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, reason = policy.allow_tool(
        ToolCall(name="edit_file", args={"path": "a.txt", "old": "x", "new": "y"})
    )
    assert allowed, reason


def test_policy_blocks_edit_file_outside_workspace(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, reason = policy.allow_tool(
        ToolCall(
            name="edit_file", args={"path": "../escape.txt", "old": "x", "new": "y"}
        )
    )
    assert not allowed
    assert "out of workspace" in reason


def test_policy_admits_grep_with_no_path_arg(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, reason = policy.allow_tool(ToolCall(name="grep", args={"pattern": "x"}))
    assert allowed, reason


def test_policy_admits_glob_with_no_path_arg(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, reason = policy.allow_tool(ToolCall(name="glob", args={"pattern": "*.py"}))
    assert allowed, reason


def test_policy_blocks_grep_path_outside_workspace(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, reason = policy.allow_tool(
        ToolCall(name="grep", args={"pattern": "x", "path": "../escape"})
    )
    assert not allowed
    assert "out of workspace" in reason
