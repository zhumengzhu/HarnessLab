"""Load skill catalog indexes from bundled, local file, or HTTPS sources."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

BUNDLED_CATALOG_SOURCE = "bundled"
_CACHE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class CatalogSkillEntry:
    catalog_id: str
    name: str
    description: str
    tags: tuple[str, ...]
    source: str
    index_source: str


def catalog_cache_dir() -> Path:
    return Path.home() / ".config" / "harnesslab" / "catalog-cache"


def _parse_tags(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, list):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    if isinstance(raw, str) and raw.strip():
        return tuple(tag.strip() for tag in raw.split(",") if tag.strip())
    return ()


def _parse_index_payload(
    data: dict[str, Any],
    *,
    index_source: str,
) -> list[CatalogSkillEntry]:
    skills_raw = data.get("skills")
    if not isinstance(skills_raw, list):
        raise ValueError(f"catalog index {index_source!r} missing skills array")
    entries: list[CatalogSkillEntry] = []
    for item in skills_raw:
        if not isinstance(item, dict):
            continue
        catalog_id = str(item.get("id") or item.get("name") or "").strip()
        name = str(item.get("name") or catalog_id).strip()
        if not catalog_id or not name:
            continue
        description = str(item.get("description") or f"Catalog skill · {name}").strip()
        source = str(item.get("source") or "").strip()
        if not source:
            continue
        entries.append(
            CatalogSkillEntry(
                catalog_id=catalog_id,
                name=name,
                description=description[:240],
                tags=_parse_tags(item.get("tags")),
                source=source,
                index_source=index_source,
            )
        )
    return entries


def _bundled_index_text() -> str:
    package = importlib.resources.files("harnesslab.skills")
    return (package / "sample-index.json").read_text(encoding="utf-8")


def _load_local_index(path: Path) -> list[CatalogSkillEntry]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"catalog index not found: {resolved}")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"catalog index root must be an object: {resolved}")
    return _parse_index_payload(data, index_source=str(resolved))


def _cache_path_for_url(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return catalog_cache_dir() / f"{digest}.json"


def _load_https_index(url: str) -> list[CatalogSkillEntry]:
    cache_path = _cache_path_for_url(url)
    if cache_path.is_file():
        age = time.time() - cache_path.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return _parse_index_payload(data, index_source=url)
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"catalog index root must be an object: {url}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return _parse_index_payload(data, index_source=url)


def load_catalog_entries(source: str) -> list[CatalogSkillEntry]:
    """Load skill entries from bundled, local index path, or HTTPS index URL."""

    normalized = source.strip()
    if not normalized:
        return []
    if normalized == BUNDLED_CATALOG_SOURCE:
        data = json.loads(_bundled_index_text())
        if not isinstance(data, dict):
            raise ValueError("bundled catalog index must be an object")
        return _parse_index_payload(data, index_source=BUNDLED_CATALOG_SOURCE)
    if normalized.startswith(("http://", "https://")):
        return _load_https_index(normalized)
    return _load_local_index(Path(normalized))


def load_all_catalog_entries(sources: tuple[str, ...]) -> list[CatalogSkillEntry]:
    merged: dict[str, CatalogSkillEntry] = {}
    for source in sources:
        for entry in load_catalog_entries(source):
            merged.setdefault(entry.catalog_id, entry)
    return [merged[key] for key in sorted(merged)]


def find_catalog_entry(
    catalog_id: str,
    sources: tuple[str, ...],
) -> CatalogSkillEntry | None:
    needle = catalog_id.strip()
    if not needle:
        return None
    for entry in load_all_catalog_entries(sources):
        if entry.catalog_id == needle or entry.name == needle:
            return entry
    return None


def resolve_catalog_source_url(entry: CatalogSkillEntry) -> str:
    source = entry.source.strip()
    if source.startswith(("http://", "https://")):
        return source
    if entry.index_source == BUNDLED_CATALOG_SOURCE:
        package = importlib.resources.files("harnesslab.skills")
        return str(package.joinpath(source))
    if entry.index_source.startswith(("http://", "https://")):
        return urljoin(entry.index_source, source)
    base = Path(entry.index_source).expanduser().resolve().parent
    return str((base / source).resolve())


def read_skill_markdown(entry: CatalogSkillEntry) -> str:
    source = entry.source.strip()
    if source.startswith(("http://", "https://")):
        response = httpx.get(source, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.text
    if entry.index_source == BUNDLED_CATALOG_SOURCE:
        package = importlib.resources.files("harnesslab.skills")
        return (package / source).read_text(encoding="utf-8")
    if entry.index_source.startswith(("http://", "https://")):
        url = urljoin(entry.index_source, source)
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.text
    base = Path(entry.index_source).expanduser().resolve().parent
    path = (base / source).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"catalog skill source not found: {path}")
    return path.read_text(encoding="utf-8")


def default_catalog_sources(
    configured: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    if configured:
        return configured
    return (BUNDLED_CATALOG_SOURCE,)
