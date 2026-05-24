"""Pytest hooks — keep application logs quiet unless HARNESSLAB_LOG is set."""

from __future__ import annotations

import os


def pytest_configure(config: object) -> None:
    _ = config
    if os.getenv("RUN_DEEPSEEK_LIVE") == "1" or os.getenv("RUN_ANTHROPIC_DEEPSEEK_LIVE") == "1":
        # Live provider lane: show INFO diagnostics unless operator overrides.
        os.environ.setdefault("HARNESSLAB_LOG", "INFO")
    else:
        os.environ.setdefault("HARNESSLAB_LOG", "WARNING")
    from harnesslab.telemetry.log import configure_logging

    configure_logging(force=True)
