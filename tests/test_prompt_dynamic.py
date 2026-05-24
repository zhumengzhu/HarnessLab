"""Tests for runtime-built prompt blocks (env, agents_md, skills, tool_guide)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from harnesslab.core.prompt import (
    build_agents_md_block,
    build_env_block,
    build_planning_block,
    build_skills_block,
    build_tool_guide_block,
)

# ---------- env ----------


def test_env_block_includes_cwd_platform_today(tmp_path: Path) -> None:
    block = build_env_block(
        tmp_path,
        today="2026-05-23",
        platform_str="TestOS-1.0",
    )
    assert block.name == "env"
    assert block.role == "system"
    assert block.origin == "dynamic:env"
    body = block.content
    assert f"cwd: {tmp_path}" in body
    assert "platform: TestOS-1.0" in body
    assert "today: 2026-05-23" in body


def test_env_block_omits_git_when_workspace_is_not_a_repo(tmp_path: Path) -> None:
    block = build_env_block(tmp_path, today="2026-05-23", platform_str="x")
    assert "git:" not in block.content


def test_env_block_reports_git_summary_when_repo_exists(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@example.com"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True
    )
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "a.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True
    )

    block = build_env_block(tmp_path, today="2026-05-23", platform_str="x")
    assert "git:" in block.content
    assert "branch: main" in block.content
    assert "clean" in block.content

    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")
    dirty = build_env_block(tmp_path, today="2026-05-23", platform_str="x")
    assert "1 change(s)" in dirty.content


# ---------- agents_md ----------


def test_agents_md_block_returns_none_when_missing(tmp_path: Path) -> None:
    assert build_agents_md_block(tmp_path) is None


def test_agents_md_block_returns_none_when_empty(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("   \n\n", encoding="utf-8")
    assert build_agents_md_block(tmp_path) is None


def test_agents_md_block_wraps_workspace_file(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Project rules\n\n- Do X\n- Do not Y\n",
        encoding="utf-8",
    )
    block = build_agents_md_block(tmp_path)
    assert block is not None
    assert block.name == "agents_md"
    assert block.role == "system"
    assert block.origin == "dynamic:agents_md:AGENTS.md"
    assert "Project rules" in block.content
    assert block.content.startswith("# AGENTS.md")


# ---------- skills ----------


def test_skills_block_returns_none_when_missing(tmp_path: Path) -> None:
    assert build_skills_block(tmp_path) is None


def test_skills_block_collects_markdown_files(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("# Research\n- source map\n", encoding="utf-8")
    (skills / "debug.md").write_text("Use reproduction-first workflow.", encoding="utf-8")
    block = build_skills_block(tmp_path)
    assert block is not None
    assert block.name == "skills"
    assert block.origin == "dynamic:skills:skills"
    assert "## Catalog" in block.content
    assert "- research" in block.content
    assert "- debug" in block.content
    assert "Pinned this session: (none)" in block.content
    assert "Selected this turn: (auto:model-picks)" in block.content
    assert "## research" in block.content
    assert "source map" in block.content
    assert "## debug" in block.content


def test_skills_block_can_filter_selected_names(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("search deeply", encoding="utf-8")
    (skills / "debug.md").write_text("repro first", encoding="utf-8")
    block = build_skills_block(tmp_path, selected_names=["debug"])
    assert block is not None
    assert "Pinned this session: (none)" in block.content
    assert "Selected this turn: debug" in block.content
    assert "- research" in block.content
    assert "## debug" in block.content
    assert "## research" not in block.content


def test_skills_block_can_show_pinned_names(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("search deeply", encoding="utf-8")
    block = build_skills_block(tmp_path, pinned_names=["research"])
    assert block is not None
    assert "Pinned this session: research" in block.content
    assert "Selected this turn: (auto:model-picks)" in block.content


# ---------- planning ----------


def test_planning_block_is_disabled_when_mode_off() -> None:
    assert build_planning_block("off") is None


def test_planning_block_uses_packaged_content_when_enabled() -> None:
    hint = build_planning_block("hint")
    required = build_planning_block("required")
    assert hint is not None
    assert required is not None
    assert hint.origin == "static:05_planning.md"
    assert "Planning mode is enabled" in hint.content
    assert "Planning mode is REQUIRED" in required.content
    assert "Plan: list 2-5 concrete steps" in hint.content


# ---------- tool_guide ----------


class _FakeTool:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description


def test_tool_guide_lists_each_tool_with_description() -> None:
    block = build_tool_guide_block(
        [
            _FakeTool("read_file", "Read text contents of a file."),
            _FakeTool("write_file", "Write text contents to a file."),
        ]
    )
    assert block.name == "tool_guide"
    assert block.origin == "dynamic:tool_guide"
    assert "`read_file`: Read text contents of a file." in block.content
    assert "`write_file`: Write text contents to a file." in block.content


def test_tool_guide_handles_empty_registry() -> None:
    block = build_tool_guide_block([])
    assert "(no tools registered)" in block.content


def test_tool_guide_skips_unnamed_entries() -> None:
    block = build_tool_guide_block([_FakeTool("", "skip me"), _FakeTool("ok", "keep")])
    assert "`ok`" in block.content
    assert "skip me" not in block.content
