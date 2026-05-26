"""Local skill catalog: list, search, and install workspace/user skills."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class SkillRecord:
    name: str
    description: str
    tags: tuple[str, ...]
    scope: str
    path: Path


def user_skills_dir() -> Path:
    return Path.home() / ".config" / "harnesslab" / "skills"


def _parse_front_matter(text: str) -> dict[str, str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}
    block = match.group(1)
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            meta[key] = value
    return meta


def _description_from_markdown(text: str, *, fallback: str) -> str:
    meta = _parse_front_matter(text)
    if meta.get("description"):
        return meta["description"][:240]
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped and not stripped.startswith("---"):
            return stripped[:240]
    return fallback


def _tags_from_markdown(text: str) -> tuple[str, ...]:
    meta = _parse_front_matter(text)
    raw = meta.get("tags", "")
    if not raw:
        return ()
    return tuple(tag.strip() for tag in raw.split(",") if tag.strip())


def _records_in_dir(directory: Path, *, scope: str) -> list[SkillRecord]:
    if not directory.is_dir():
        return []
    records: list[SkillRecord] = []
    for path in sorted(directory.glob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        name = path.stem
        records.append(
            SkillRecord(
                name=name,
                description=_description_from_markdown(
                    text,
                    fallback=f"Workspace skill · {name}",
                ),
                tags=_tags_from_markdown(text),
                scope=scope,
                path=path.resolve(),
            )
        )
    return records


def list_skill_records(workspace_root: Path) -> list[SkillRecord]:
    """List workspace skills first; user-global skills fill gaps by name."""

    workspace_records = _records_in_dir(workspace_root / "skills", scope="workspace")
    by_name = {record.name: record for record in workspace_records}
    for record in _records_in_dir(user_skills_dir(), scope="user"):
        by_name.setdefault(record.name, record)
    return [by_name[name] for name in sorted(by_name)]


def search_skills(workspace_root: Path, query: str) -> list[SkillRecord]:
    needle = query.strip().lower()
    if not needle:
        return list_skill_records(workspace_root)
    hits: list[SkillRecord] = []
    for record in list_skill_records(workspace_root):
        haystack = " ".join(
            [record.name, record.description, record.scope, *record.tags]
        ).lower()
        if needle in haystack:
            hits.append(record)
    return hits


def install_skill(
    workspace_root: Path,
    source: Path,
    *,
    scope: str = "workspace",
) -> Path:
    """Copy a skill markdown file into workspace or user skills directory."""

    src = source.expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"skill source not found: {src}")
    if src.suffix.lower() != ".md":
        raise ValueError("skill install expects a .md file")

    if scope == "user":
        dest_dir = user_skills_dir()
    elif scope == "workspace":
        dest_dir = workspace_root.resolve() / "skills"
    else:
        raise ValueError("scope must be 'workspace' or 'user'")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest
