"""Tests for semantic memory FTS store."""

from __future__ import annotations

from harnesslab.memory.semantic_sqlite import SqliteSemanticMemoryStore


def test_semantic_memory_search(tmp_path) -> None:
    db = tmp_path / "mem.sqlite"
    store = SqliteSemanticMemoryStore(db)
    store.upsert("doc1", "HarnessLab agent harness research notes")
    store.upsert("doc2", "unrelated cooking recipe")
    hits = store.search("harness research")
    assert hits
    assert hits[0].key == "doc1"
    store.close()
