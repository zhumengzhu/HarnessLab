"""Tests for optional model stream sink context."""

from __future__ import annotations

from harnesslab.core.stream_context import (
    bind_stream_sink,
    emit_stream_delta,
    reset_stream_sink,
    stream_sink_active,
)


def test_emit_stream_delta_invokes_bound_sink() -> None:
    seen: list[tuple[str, str, int]] = []

    def sink(kind: str, text: str, step_index: int) -> None:
        seen.append((kind, text, step_index))

    token = bind_stream_sink(sink, step_index=2)
    assert stream_sink_active()
    emit_stream_delta("reasoning", "abc")
    reset_stream_sink(token)
    assert not stream_sink_active()
    assert seen == [("reasoning", "abc", 2)]
