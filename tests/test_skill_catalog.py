"""Tests for skill catalog search/install."""

from __future__ import annotations

from pathlib import Path

from harnesslab.skills.catalog import install_skill, list_skill_records, search_skills


def test_search_skills_matches_name_and_description(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "compact.md").write_text(
        "# Compact\n\nSummarize older context.\n",
        encoding="utf-8",
    )
    (skills / "humanizer.md").write_text(
        "---\ndescription: Rewrite AI tone\ntags: writing, tone\n---\n\n# Humanizer\n",
        encoding="utf-8",
    )
    hits = search_skills(tmp_path, "tone")
    assert [record.name for record in hits] == ["humanizer"]


def test_install_skill_copies_into_workspace(tmp_path: Path) -> None:
    src = tmp_path / "incoming.md"
    src.write_text("# Demo skill\n", encoding="utf-8")
    dest = install_skill(tmp_path, src, scope="workspace")
    assert dest.is_file()
    assert dest.name == "incoming.md"
    assert list_skill_records(tmp_path)


def test_list_skill_records_prefers_workspace_over_user(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_skill = tmp_path / "skills"
    workspace_skill.mkdir()
    (workspace_skill / "shared.md").write_text("# workspace\n", encoding="utf-8")

    user_root = tmp_path / "user"
    user_skills = user_root / ".config" / "harnesslab" / "skills"
    user_skills.mkdir(parents=True)
    (user_skills / "shared.md").write_text("# user\n", encoding="utf-8")
    (user_skills / "global-only.md").write_text("# global\n", encoding="utf-8")

    monkeypatch.setattr(
        "harnesslab.skills.catalog.user_skills_dir",
        lambda: user_skills,
    )
    records = list_skill_records(tmp_path)
    by_name = {record.name: record for record in records}
    assert by_name["shared"].scope == "workspace"
    assert by_name["global-only"].scope == "user"
