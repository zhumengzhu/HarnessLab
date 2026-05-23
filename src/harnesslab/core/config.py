from __future__ import annotations

from dataclasses import dataclass

DEFAULT_OUTPUT_BYTES_CAP = 65536
DEFAULT_SHELL_TIMEOUT_SECONDS = 5

# Phase 2.4 defaults. The numbers are intentionally generous for the
# MVP; the focus is to exercise the compaction code path, not to fit a
# specific model's hard cap. Real adapters can tighten these via the
# CLI / config knobs in a later phase.
DEFAULT_CONTEXT_WINDOW_TOKENS = 16000
DEFAULT_COMPACTION_THRESHOLD_TOKENS = 12000
DEFAULT_COMPACTION_KEEP_LAST_MESSAGES = 4


@dataclass(frozen=True)
class RuntimeLimits:
    """Resource limits applied uniformly across tools and the loop.

    Centralizing these knobs makes them configurable from one place
    (CLI / config file) and trivially overridable in tests.
    """

    output_bytes_cap: int = DEFAULT_OUTPUT_BYTES_CAP
    shell_timeout_seconds: int = DEFAULT_SHELL_TIMEOUT_SECONDS

    # Context / compaction.
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    compaction_threshold_tokens: int = DEFAULT_COMPACTION_THRESHOLD_TOKENS
    compaction_keep_last_messages: int = DEFAULT_COMPACTION_KEEP_LAST_MESSAGES
