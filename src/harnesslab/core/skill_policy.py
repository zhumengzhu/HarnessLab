"""Session-scoped skill command parsing and selection helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from harnesslab.core.models import Message

SKILL_PREFIX = "/skill"
SKILL_STATE_PREFIX = "[skills:selected]"


@dataclass(frozen=True)
class SkillCommand:
    kind: str
    name: str | None = None


def parse_skill_command(user_input: str) -> SkillCommand | None:
    text = user_input.strip()
    if not text.startswith(SKILL_PREFIX):
        return None
    rest = text[len(SKILL_PREFIX) :].strip()
    if not rest or rest.lower() == "list":
        return SkillCommand(kind="list")
    parts = rest.split()
    head = parts[0].lower()
    if head == "add" and len(parts) >= 2:
        return SkillCommand(kind="add", name=parts[1].strip())
    if head == "remove" and len(parts) >= 2:
        return SkillCommand(kind="remove", name=parts[1].strip())
    if head == "clear":
        return SkillCommand(kind="clear")
    # Shortcut: /skill <name>
    return SkillCommand(kind="add", name=parts[0].strip())


def list_skills(workspace_root: Path | None) -> list[str]:
    if workspace_root is None:
        return []
    skills_dir = workspace_root / "skills"
    if not skills_dir.is_dir():
        return []
    names = [path.stem for path in sorted(skills_dir.glob("*.md")) if path.is_file()]
    return [name for name in names if name]


def format_skill_state_message(selected: list[str]) -> str:
    body = ",".join(selected)
    return f"{SKILL_STATE_PREFIX} {body}".rstrip()


def selected_skills_from_messages(messages: list[Message]) -> list[str]:
    for msg in reversed(messages):
        if msg.role != "system":
            continue
        text = msg.content.strip()
        if not text.startswith(SKILL_STATE_PREFIX):
            continue
        raw = text[len(SKILL_STATE_PREFIX) :].strip()
        if not raw:
            return []
        out: list[str] = []
        for item in raw.split(","):
            name = item.strip()
            if name and name not in out:
                out.append(name)
        return out
    return []


def choose_skill_names(
    *,
    available: list[str],
    pinned: list[str],
    user_input: str,
    max_skills: int = 3,
) -> list[str]:
    """Pick session skill names with pinned-first, then lexical overlap."""

    if max_skills < 1:
        return []

    chosen: list[str] = []
    for name in pinned:
        if name in available and name not in chosen:
            chosen.append(name)
            if len(chosen) >= max_skills:
                return chosen

    query_tokens = _tokenize(user_input)
    scored: list[tuple[int, str]] = []
    for name in available:
        if name in chosen:
            continue
        score = 0
        name_tokens = _tokenize(name.replace("-", " ").replace("_", " "))
        score += len(query_tokens.intersection(name_tokens))
        if query_tokens and any(tok in name.lower() for tok in query_tokens):
            score += 1
        scored.append((score, name))

    scored.sort(key=lambda item: (-item[0], item[1]))
    for score, name in scored:
        if score <= 0 and query_tokens:
            continue
        chosen.append(name)
        if len(chosen) >= max_skills:
            break

    if not chosen:
        return available[: max_skills]
    return chosen


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())}
