from __future__ import annotations

from dataclasses import dataclass

DEFAULT_OUTPUT_BYTES_CAP = 65536
DEFAULT_SHELL_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class RuntimeLimits:
    """Resource limits applied uniformly across tools.

    Centralizing these knobs makes them configurable from one place
    (CLI / config file) and trivially overridable in tests.
    """

    output_bytes_cap: int = DEFAULT_OUTPUT_BYTES_CAP
    shell_timeout_seconds: int = DEFAULT_SHELL_TIMEOUT_SECONDS
