"""W3C-compatible trace and span id generation."""

from __future__ import annotations

import secrets


def new_trace_id() -> str:
    """128-bit trace id as 32 lowercase hex chars."""

    return secrets.token_hex(16)


def new_span_id() -> str:
    """64-bit span id as 16 lowercase hex chars."""

    return secrets.token_hex(8)
