"""Local and catalog skill discovery, search, install, and remove."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from harnesslab.skills.index_loader import (
    BUNDLED_CATALOG_SOURCE,
    CatalogSkillEntry,
    default_catalog_sources,
    find_catalog_entry,
    load_all_catalog_entries,
    read_skill_markdown,
)

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class SkillRecord:
    name: str
    description: str
    tags: tuple[str, ...]
    scope: str
    path: Path | None = None
    catalog_id: str | None = None


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


def validate_skill_markdown(text: str) -> None:
    if not text.strip():
        raise ValueError("skill markdown is empty")
    if len(text) > 512_000:
        raise ValueError("skill markdown exceeds 512KB limit")


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


def _installed_records(workspace_root: Path) -> list[SkillRecord]:
    workspace_records = _records_in_dir(workspace_root / "skills", scope="workspace")
    by_name = {record.name: record for record in workspace_records}
    for record in _records_in_dir(user_skills_dir(), scope="user"):
        by_name.setdefault(record.name, record)
    return [by_name[name] for name in sorted(by_name)]


def _catalog_records(
    workspace_root: Path,
    catalog_sources: tuple[str, ...],
) -> list[SkillRecord]:
    installed_names = {record.name for record in _installed_records(workspace_root)}
    records: list[SkillRecord] = []
    for entry in load_all_catalog_entries(catalog_sources):
        if entry.name in installed_names:
            continue
        records.append(_record_from_catalog_entry(entry))
    return records


def _record_from_catalog_entry(entry: CatalogSkillEntry) -> SkillRecord:
    return SkillRecord(
        name=entry.name,
        description=entry.description,
        tags=entry.tags,
        scope="catalog",
        path=None,
        catalog_id=entry.catalog_id,
    )


def list_skill_records(
    workspace_root: Path,
    *,
    catalog_sources: tuple[str, ...] | None = None,
    include_catalog: bool = False,
) -> list[SkillRecord]:
    """List installed skills; optionally append catalog-only entries."""

    installed = _installed_records(workspace_root)
    if not include_catalog:
        return installed
    sources = default_catalog_sources(catalog_sources)
    return installed + _catalog_records(workspace_root, sources)


def search_skills(
    workspace_root: Path,
    query: str,
    *,
    catalog_sources: tuple[str, ...] | None = None,
) -> list[SkillRecord]:
    needle = query.strip().lower()
    records = list_skill_records(
        workspace_root,
        catalog_sources=catalog_sources,
        include_catalog=True,
    )
    if not needle:
        return records
    hits: list[SkillRecord] = []
    for record in records:
        haystack = " ".join(
            [record.name, record.description, record.scope, *record.tags]
        ).lower()
        if needle in haystack:
            hits.append(record)
    return hits


def preview_skill(
    workspace_root: Path,
    *,
    name: str | None = None,
    catalog_id: str | None = None,
    catalog_sources: tuple[str, ...] | None = None,
) -> str:
    """Return markdown preview for an installed skill or catalog entry."""

    if catalog_id:
        sources = default_catalog_sources(catalog_sources)
        entry = find_catalog_entry(catalog_id, sources)
        if entry is None:
            raise FileNotFoundError(f"catalog skill not found: {catalog_id}")
        return read_skill_markdown(entry)
    if not name:
        raise ValueError("name or catalog_id is required")
    for record in _installed_records(workspace_root):
        if record.name == name and record.path is not None:
            return record.path.read_text(encoding="utf-8")
    sources = default_catalog_sources(catalog_sources)
    entry = find_catalog_entry(name, sources)
    if entry is None:
        raise FileNotFoundError(f"skill not found: {name}")
    return read_skill_markdown(entry)


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
    validate_skill_markdown(src.read_text(encoding="utf-8"))
    return _write_skill_markdown(
        workspace_root,
        src.read_text(encoding="utf-8"),
        filename=src.name,
        scope=scope,
    )


def install_skill_from_catalog(
    workspace_root: Path,
    catalog_id: str,
    *,
    scope: str = "workspace",
    catalog_sources: tuple[str, ...] | None = None,
) -> Path:
    """Install a catalog skill by id into workspace or user skills directory."""

    sources = default_catalog_sources(catalog_sources)
    entry = find_catalog_entry(catalog_id, sources)
    if entry is None:
        raise FileNotFoundError(f"catalog skill not found: {catalog_id}")
    text = read_skill_markdown(entry)
    validate_skill_markdown(text)
    return _write_skill_markdown(
        workspace_root,
        text,
        filename=f"{entry.name}.md",
        scope=scope,
    )


def remove_skill(
    workspace_root: Path,
    name: str,
    *,
    scope: str = "workspace",
) -> Path:
    """Remove an installed skill markdown file."""

    stem = name.strip()
    if not stem:
        raise ValueError("skill name is required")
    if scope == "user":
        target = user_skills_dir() / f"{stem}.md"
    elif scope == "workspace":
        target = workspace_root.resolve() / "skills" / f"{stem}.md"
    else:
        raise ValueError("scope must be 'workspace' or 'user'")
    if not target.is_file():
        raise FileNotFoundError(f"installed skill not found: {target}")
    target.unlink()
    return target


def skill_installed_event_payload(
    *,
    name: str,
    scope: str,
    source: str,
) -> dict[str, str]:
    """Optional audit payload for ``skill_installed`` trace events."""

    return {
        "event_type": "skill_installed",
        "name": name,
        "scope": scope,
        "source": source,
    }


def _write_skill_markdown(
    workspace_root: Path,
    text: str,
    *,
    filename: str,
    scope: str,
) -> Path:
    if scope == "user":
        dest_dir = user_skills_dir()
    elif scope == "workspace":
        dest_dir = workspace_root.resolve() / "skills"
    else:
        raise ValueError("scope must be 'workspace' or 'user'")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_text(text, encoding="utf-8")
    return dest


def _download_skill_to_temp(url: str) -> Path:
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    suffix = ".md"
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as tmp:
        tmp.write(response.text)
        return Path(tmp.name)


def install_skill_from_url(
    workspace_root: Path,
    url: str,
    *,
    scope: str = "workspace",
) -> Path:
    """Download a remote skill markdown file and install it."""

    tmp = _download_skill_to_temp(url)
    try:
        return install_skill(workspace_root, tmp, scope=scope)
    finally:
        tmp.unlink(missing_ok=True)


__all__ = [
    "BUNDLED_CATALOG_SOURCE",
    "SkillRecord",
    "install_skill",
    "install_skill_from_catalog",
    "install_skill_from_url",
    "list_skill_records",
    "preview_skill",
    "remove_skill",
    "search_skills",
    "skill_installed_event_payload",
    "user_skills_dir",
]
