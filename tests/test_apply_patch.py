"""Tests for apply_patch unified-diff tool."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.models import ToolCall
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.tools.patch import ApplyPatchTool, apply_unified_patch, parse_unified_patch


def test_parse_unified_patch_single_hunk() -> None:
    patch = """\
@@ -1,3 +1,3 @@
 line1
-old
+new
 line3
"""
    hunks = parse_unified_patch(patch)
    assert len(hunks) == 1
    assert hunks[0].old_start == 1
    assert hunks[0].old_count == 3


def test_apply_unified_patch_replaces_line() -> None:
    original = "line1\nold\nline3\n"
    patch = """\
@@ -1,3 +1,3 @@
 line1
-old
+new
 line3
"""
    assert apply_unified_patch(original, patch) == "line1\nnew\nline3\n"


def test_apply_unified_patch_context_mismatch() -> None:
    original = "alpha\nbeta\n"
    patch = """\
@@ -1,2 +1,2 @@
 alpha
-beta
+gamma
"""
    try:
        apply_unified_patch(original.replace("beta", "WRONG"), patch)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "context" in str(exc)


def test_apply_patch_tool_writes_file(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    tool = ApplyPatchTool(tmp_path)
    patch = """\
@@ -2,1 +2,1 @@
-two
+2
"""
    result = tool.execute(
        ToolCall(name="apply_patch", args={"path": "a.txt", "patch": patch})
    )
    assert result.ok, result.error
    assert target.read_text(encoding="utf-8") == "one\n2\nthree\n"


def test_apply_patch_tool_rejects_missing_file(tmp_path: Path) -> None:
    tool = ApplyPatchTool(tmp_path)
    result = tool.execute(
        ToolCall(
            name="apply_patch",
            args={"path": "missing.txt", "patch": "@@ -1,1 +1,1 @@\n-a\n+b\n"},
        )
    )
    assert not result.ok
    assert "not found" in (result.error or "")


def test_policy_allows_apply_patch_inside_workspace(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, _ = policy.allow_tool(
        ToolCall(name="apply_patch", args={"path": "a.txt", "patch": "@@ -1,1 +1,1 @@\n"})
    )
    assert allowed


def test_policy_blocks_apply_patch_outside_workspace(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, reason = policy.allow_tool(
        ToolCall(
            name="apply_patch",
            args={"path": "../escape.txt", "patch": "@@ -1,1 +1,1 @@\n"},
        )
    )
    assert not allowed
    assert "workspace" in reason
