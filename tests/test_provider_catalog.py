"""Tests for provider model catalog (Post-MVP P1)."""

from __future__ import annotations

import pytest

from harnesslab.providers.catalog import CatalogEntry, ModelCatalog


def test_builtin_catalog_loads_deepseek_models() -> None:
    catalog = ModelCatalog()
    ids = catalog.list_model_ids()
    assert "deepseek-v4-flash" in ids
    assert "deepseek-v4-pro" in ids
    assert "claude-sonnet-4-6" in ids
    assert "gpt-5-mini" in ids
    assert "gemini-2.5-flash" in ids
    assert "gemini-3-flash-preview" in ids


def test_catalog_get_returns_entry_fields() -> None:
    entry = ModelCatalog().get("deepseek-v4-flash")
    assert entry.provider == "deepseek"
    assert entry.api_family == "openai_chat"
    assert entry.context_window == 1_048_576
    assert entry.thinking_default == "disabled"
    assert entry.reasoning_support == "native"


def test_catalog_resolve_accepts_provider_ref() -> None:
    entry = ModelCatalog().resolve("deepseek/deepseek-v4-pro")
    assert entry.model_id == "deepseek-v4-pro"


def test_deepseek_catalog_thinking_schema() -> None:
    flash = ModelCatalog().get("deepseek-v4-flash")
    pro = ModelCatalog().get("deepseek-v4-pro")
    assert flash.thinking_schema == "toggle"
    assert pro.thinking_schema == "toggle"


def test_gemini_catalog_thinking_schema() -> None:
    budget = ModelCatalog().get("gemini-2.5-flash")
    level = ModelCatalog().get("gemini-3-flash-preview")
    assert budget.thinking_schema == "budget"
    assert level.thinking_schema == "level"


def test_catalog_get_unknown_raises() -> None:
    with pytest.raises(KeyError, match="unknown catalog model_id"):
        ModelCatalog().get("not-a-model")


def test_custom_catalog_entries() -> None:
    custom = CatalogEntry(
        model_id="mock-model",
        provider="mock",
        api_family="openai_chat",
        context_window=8192,
        thinking_default="disabled",
        reasoning_support="none",
    )
    catalog = ModelCatalog(entries={"mock-model": custom})
    assert catalog.get("mock-model") is custom
