"""Tests for composer slash-command metadata."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.composer_commands import composer_commands_payload


def test_composer_commands_payload_lists_builtins_and_skills(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("# Deep research\nLook widely.", encoding="utf-8")

    payload = composer_commands_payload(tmp_path)
    names = {item["name"] for item in payload["commands"]}
    assert "remember" in names
    assert "remember-global" in names
    assert payload["skills"][0]["name"] == "research"
    assert payload["skills"][0]["insert"] == "/research "
    assert "Deep research" in payload["skills"][0]["description"]
