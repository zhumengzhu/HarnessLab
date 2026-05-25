from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.core.models import ArtifactMeta


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}
        self._meta: dict[str, ArtifactMeta] = {}

    def put(self, data: bytes, *, mime: str, session_id: str, artifact_id: str) -> str:
        now = datetime.now(UTC)
        meta = ArtifactMeta(
            id=artifact_id,
            session_id=session_id,
            mime=mime,
            size_bytes=len(data),
            sha256=_sha256_hex(data),
            created_at=now,
        )
        self._blobs[artifact_id] = data
        self._meta[artifact_id] = meta
        return artifact_id

    def get(self, ref: str) -> bytes:
        if ref not in self._blobs:
            raise KeyError(f"artifact not found: {ref}")
        return self._blobs[ref]

    def metadata(self, ref: str) -> ArtifactMeta:
        if ref not in self._meta:
            raise KeyError(f"artifact not found: {ref}")
        return self._meta[ref]

    def list(self, *, session_id: str | None = None, limit: int = 50) -> list[ArtifactMeta]:
        rows = list(self._meta.values())
        if session_id is not None:
            rows = [m for m in rows if m.session_id == session_id]
        rows.sort(key=lambda m: m.created_at, reverse=True)
        return rows[:limit]


def _sha256_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
