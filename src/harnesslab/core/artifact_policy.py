"""Store oversized tool output in ArtifactStorePort when configured."""

from __future__ import annotations

from harnesslab.core.contracts import ArtifactStorePort, IdPort
from harnesslab.core.models import ToolResult


def maybe_externalize_tool_output(
    output: str,
    *,
    artifact_store: ArtifactStorePort | None,
    ids: IdPort,
    session_id: str,
    threshold_bytes: int | None,
    preview_bytes: int = 512,
) -> ToolResult:
    """Return a ToolResult with truncated output and optional artifact_ref."""

    if artifact_store is None or threshold_bytes is None or threshold_bytes <= 0:
        return ToolResult(ok=True, output=output)
    encoded = output.encode("utf-8")
    if len(encoded) <= threshold_bytes:
        return ToolResult(ok=True, output=output)

    ref = ids.new_id("art")
    artifact_store.put(
        encoded,
        mime="text/plain; charset=utf-8",
        session_id=session_id,
        artifact_id=ref,
    )
    preview = output[:preview_bytes]
    if len(output) > preview_bytes:
        preview = f"{preview}\n...(stored as artifact {ref}, {len(encoded)} bytes)"
    else:
        preview = f"{preview}\n(stored as artifact {ref}, {len(encoded)} bytes)"
    return ToolResult(ok=True, output=preview, artifact_ref=ref)
