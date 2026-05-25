from __future__ import annotations

from harnesslab.artifact.in_memory import InMemoryArtifactStore
from harnesslab.core.artifact_policy import maybe_externalize_tool_output
from harnesslab.core.runtime import SeqIdProvider


def test_maybe_externalize_below_threshold() -> None:
    store = InMemoryArtifactStore()
    ids = SeqIdProvider()
    result = maybe_externalize_tool_output(
        "small",
        artifact_store=store,
        ids=ids,
        session_id="ses_1",
        threshold_bytes=100,
    )
    assert result.artifact_ref is None
    assert result.output == "small"


def test_maybe_externalize_stores_large_output() -> None:
    store = InMemoryArtifactStore()
    ids = SeqIdProvider()
    big = "x" * 200
    result = maybe_externalize_tool_output(
        big,
        artifact_store=store,
        ids=ids,
        session_id="ses_1",
        threshold_bytes=50,
    )
    assert result.artifact_ref is not None
    assert "stored as artifact" in result.output
    assert store.get(result.artifact_ref) == big.encode("utf-8")
