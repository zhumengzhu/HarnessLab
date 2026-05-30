"""Pytest hooks — keep application logs quiet unless HARNESSLAB_LOG is set."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import mkstemp

import pytest


def pytest_configure(config: object) -> None:
    _ = config
    if os.getenv("RUN_DEEPSEEK_LIVE") == "1" or os.getenv("RUN_ANTHROPIC_DEEPSEEK_LIVE") == "1":
        # Live provider lane: show INFO diagnostics unless operator overrides.
        os.environ.setdefault("HARNESSLAB_LOG", "INFO")
    else:
        os.environ.setdefault("HARNESSLAB_LOG", "WARNING")
    from harnesslab.telemetry.log import configure_logging

    configure_logging(force=True)


@pytest.fixture(autouse=True)
def _isolate_operator_pricing_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent developer ``~/.config/harnesslab/pricing.json`` from affecting tests."""

    if os.getenv("HARNESSLAB_PRICING_CONFIG"):
        yield
        return
    fd, path = mkstemp(suffix=".json")
    os.close(fd)
    pricing_path = Path(path)
    pricing_path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("HARNESSLAB_PRICING_CONFIG", str(pricing_path))
    from harnesslab.providers.pricing import reset_pricing_cache

    reset_pricing_cache()
    yield
    reset_pricing_cache()
    pricing_path.unlink(missing_ok=True)
