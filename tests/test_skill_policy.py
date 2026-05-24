"""Tests for session-scoped skill policy helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from harnesslab.core.models import Message
from harnesslab.core.skill_policy import (
    SkillCommand,
    choose_skill_names,
    format_skill_state_message,
    list_skills,
    parse_skill_command,
    selected_skills_from_messages,
)


def _msg(role: str, content: str) -> Message:
    return Message(
        id=f"msg_{abs(hash((role, content))) % 10000}",
        role=role,  # type: ignore[arg-type]
        content=content,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        session_id="ses_test",
    )


def test_parse_skill_command_variants() -> None:
    assert parse_skill_command("hello") is None
    assert parse_skill_command("/skill") == SkillCommand(kind="list")
    assert parse_skill_command("/skill list") == SkillCommand(kind="list")
    assert parse_skill_command("/skill add research") == SkillCommand(kind="add", name="research")
    assert parse_skill_command("/skill remove debug") == SkillCommand(
        kind="remove", name="debug"
    )
    assert parse_skill_command("/skill clear") == SkillCommand(kind="clear")
    assert parse_skill_command("/skill research") == SkillCommand(kind="add", name="research")


def test_list_skills_reads_workspace_directory(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("x", encoding="utf-8")
    (skills / "debug.md").write_text("y", encoding="utf-8")
    assert list_skills(tmp_path) == ["debug", "research"]


def test_selected_skills_from_messages_uses_latest_state_message() -> None:
    messages = [
        _msg("system", format_skill_state_message(["research"])),
        _msg("assistant", "ok"),
        _msg("system", format_skill_state_message(["debug", "research"])),
    ]
    assert selected_skills_from_messages(messages) == ["debug", "research"]


def test_choose_skill_names_prefers_pinned_then_overlap() -> None:
    chosen = choose_skill_names(
        available=["research", "debug", "frontend"],
        pinned=["debug"],
        user_input="investigate frontend rendering issue",
        max_skills=2,
    )
    assert chosen[0] == "debug"
    assert "frontend" in chosen
