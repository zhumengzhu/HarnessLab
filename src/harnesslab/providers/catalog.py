"""Static model catalog for provider layer (Post-MVP P1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ReasoningSupport = Literal["native", "proxy", "none"]

_CATALOG_DIR = Path(__file__).resolve().parent / "catalog"


ThinkingSchema = Literal["none", "budget", "level", "toggle"]


@dataclass(frozen=True)
class CatalogEntry:
    model_id: str
    provider: str
    api_family: str
    context_window: int
    thinking_default: str
    reasoning_support: ReasoningSupport = "none"
    thinking_schema: ThinkingSchema = "none"


def _entry_from_dict(raw: dict[str, object]) -> CatalogEntry:
    model_id = raw.get("model_id")
    provider = raw.get("provider")
    api_family = raw.get("api_family")
    context_window = raw.get("context_window")
    thinking_default = raw.get("thinking_default")
    reasoning_support = raw.get("reasoning_support", "none")
    thinking_schema = raw.get("thinking_schema", "none")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("catalog entry missing model_id")
    if not isinstance(provider, str) or not provider:
        raise ValueError(f"catalog entry {model_id!r} missing provider")
    if not isinstance(api_family, str) or not api_family:
        raise ValueError(f"catalog entry {model_id!r} missing api_family")
    if not isinstance(context_window, int) or context_window <= 0:
        raise ValueError(f"catalog entry {model_id!r} missing context_window")
    if not isinstance(thinking_default, str):
        raise ValueError(f"catalog entry {model_id!r} missing thinking_default")
    if reasoning_support not in {"native", "proxy", "none"}:
        raise ValueError(
            f"catalog entry {model_id!r} has invalid reasoning_support: {reasoning_support!r}"
        )
    if thinking_schema not in {"none", "budget", "level", "toggle"}:
        raise ValueError(
            f"catalog entry {model_id!r} has invalid thinking_schema: {thinking_schema!r}"
        )
    return CatalogEntry(
        model_id=model_id,
        provider=provider,
        api_family=api_family,
        context_window=context_window,
        thinking_default=thinking_default,
        reasoning_support=reasoning_support,  # type: ignore[arg-type]
        thinking_schema=thinking_schema,  # type: ignore[arg-type]
    )


def _load_builtin_catalog() -> dict[str, CatalogEntry]:
    entries: dict[str, CatalogEntry] = {}
    if not _CATALOG_DIR.is_dir():
        return entries
    for path in sorted(_CATALOG_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"catalog file {path.name} must contain a JSON object")
        entry = _entry_from_dict(raw)
        entries[entry.model_id] = entry
    return entries


class ModelCatalog:
    """Lookup table for model metadata keyed by ``model_id``."""

    def __init__(self, entries: dict[str, CatalogEntry] | None = None) -> None:
        self._entries = dict(entries if entries is not None else _load_builtin_catalog())

    def get(self, model_id: str) -> CatalogEntry:
        try:
            return self._entries[model_id]
        except KeyError as exc:
            raise KeyError(f"unknown catalog model_id: {model_id}") from exc

    def resolve(self, ref: str) -> CatalogEntry:
        """Resolve ``provider/model`` or bare ``model_id``."""

        model_id = ref.split("/", 1)[-1] if "/" in ref else ref
        return self.get(model_id)

    def list_model_ids(self) -> list[str]:
        return sorted(self._entries)
