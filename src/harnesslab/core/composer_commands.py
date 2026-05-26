"""Slash-command metadata for the Web UI composer palette."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harnesslab.core.skill_policy import list_skills

_BUILTIN_COMMANDS: tuple[dict[str, str], ...] = (
    {
        "name": "remember",
        "usage": "/remember <text>",
        "description": "Save a note to this session's memory",
        "insert": "/remember ",
        "kind": "builtin",
    },
    {
        "name": "remember-global",
        "usage": "/remember-global <text>",
        "description": "Save a note visible to all sessions in this workspace",
        "insert": "/remember-global ",
        "kind": "builtin",
    },
    {
        "name": "compact",
        "usage": "/compact",
        "description": "Summarize older messages now and free context window",
        "insert": "/compact",
        "kind": "builtin",
    },
    {
        "name": "skill",
        "usage": "/skill list",
        "description": "List available skills and pinned skills for this session",
        "insert": "/skill list",
        "kind": "admin",
    },
)


def _skill_description(workspace_root: Path, name: str) -> str:
    path = workspace_root / "skills" / f"{name}.md"
    if not path.is_file():
        return f"Workspace skill · {name}"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return f"Workspace skill · {name}"
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return f"Workspace skill · {name}"


def composer_commands_payload(workspace_root: Path | None) -> dict[str, Any]:
    """Return slash commands and workspace skills for the composer menu."""

    root = workspace_root or Path(".")
    skills: list[dict[str, str]] = []
    for name in list_skills(root):
        skills.append(
            {
                "name": name,
                "usage": f"/{name}",
                "description": _skill_description(root, name),
                "insert": f"/{name}",
                "kind": "skill",
            }
        )
    return {
        "commands": list(_BUILTIN_COMMANDS),
        "skills": skills,
    }
