from __future__ import annotations

import pytest

from harnesslab.artifact.in_memory import InMemoryArtifactStore
from harnesslab.artifact.sqlite_store import SqliteArtifactStore
from harnesslab.core.contracts import ArtifactStorePort
from harnesslab.core.models import ArtifactMeta, Session
from harnesslab.session.sqlite_store import SqliteSessionStore


@pytest.fixture(params=["in_memory", "sqlite"])
def artifact_store(request: pytest.FixtureRequest, tmp_path) -> ArtifactStorePort:
    if request.param == "in_memory":
        yield InMemoryArtifactStore()
        return
    db = tmp_path / "state.sqlite"
    sessions = SqliteSessionStore(db)
    for sid in ("ses_test", "ses_a", "ses_b"):
        sessions.create(Session(id=sid, goal="artifact test"))
    sessions.close()
    store = SqliteArtifactStore(db, workspace_root=tmp_path)
    yield store
    store.close()


def test_artifact_store_put_get_metadata(artifact_store: ArtifactStorePort) -> None:
    ref = artifact_store.put(
        b"hello artifact",
        mime="text/plain",
        session_id="ses_test",
        artifact_id="art_test1",
    )
    assert ref == "art_test1"
    assert artifact_store.get(ref) == b"hello artifact"
    meta = artifact_store.metadata(ref)
    assert isinstance(meta, ArtifactMeta)
    assert meta.session_id == "ses_test"
    assert meta.size_bytes == len(b"hello artifact")


def test_artifact_store_list_filters_session(artifact_store: ArtifactStorePort) -> None:
    artifact_store.put(b"a", mime="text/plain", session_id="ses_a", artifact_id="art_a")
    artifact_store.put(b"b", mime="text/plain", session_id="ses_b", artifact_id="art_b")
    listed = artifact_store.list(session_id="ses_a", limit=10)
    assert len(listed) == 1
    assert listed[0].id == "art_a"
