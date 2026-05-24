"""Tests for harnesslab.telemetry.log configuration."""

from __future__ import annotations

import logging

import pytest

from harnesslab.telemetry import log as hl_log


@pytest.fixture(autouse=True)
def _reset_logging_config() -> None:
    hl_log._CONFIGURED = False
    root = logging.getLogger("harnesslab")
    root.handlers.clear()
    yield
    hl_log._CONFIGURED = False
    root.handlers.clear()


def test_get_logger_uses_harnesslab_prefix() -> None:
    hl_log.configure_logging("DEBUG", force=True)
    logger = hl_log.get_logger("core.loop")
    assert logger.name == "harnesslab.core.loop"


def test_configure_logging_respects_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    hl_log.configure_logging("ERROR", force=True)
    logger = hl_log.get_logger("test")
    assert logger.level == logging.NOTSET
    assert logging.getLogger("harnesslab").level == logging.ERROR


def test_default_level_warning_under_pytest() -> None:
    assert hl_log._default_level_name() == "WARNING"


def test_default_level_info_outside_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(hl_log, "_running_under_pytest", lambda: False)
    assert hl_log._default_level_name() == "INFO"
