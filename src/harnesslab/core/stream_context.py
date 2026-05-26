"""Optional token-level stream sink for live Web UI deltas.

Models and the loop emit ``reasoning`` / ``assistant`` text chunks when a
sink is registered (typically for one SSE turn). Trace replay does not
depend on these events — they are volatile UX-only.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Literal

StreamDeltaKind = Literal["reasoning", "assistant"]
StreamDeltaFn = Callable[[StreamDeltaKind, str, int], None]

_stream_sink: ContextVar[StreamDeltaFn | None] = ContextVar(
    "harnesslab_stream_sink", default=None
)
_step_index: ContextVar[int] = ContextVar("harnesslab_stream_step_index", default=0)


def bind_stream_sink(
    sink: StreamDeltaFn | None, *, step_index: int = 0
) -> Token[StreamDeltaFn | None]:
    """Register a delta sink for the current async/thread context."""

    _step_index.set(step_index)
    return _stream_sink.set(sink)


def reset_stream_sink(token: Token[StreamDeltaFn | None]) -> None:
    _stream_sink.reset(token)


def set_stream_step_index(step_index: int) -> None:
    _step_index.set(step_index)


def emit_stream_delta(kind: StreamDeltaKind, text: str) -> None:
    if not text:
        return
    sink = _stream_sink.get()
    if sink is None:
        return
    sink(kind, text, _step_index.get())


def stream_sink_active() -> bool:
    return _stream_sink.get() is not None
