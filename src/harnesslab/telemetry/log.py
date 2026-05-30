"""Application logging for HarnessLab (stdlib ``logging``).

Structured runtime spans belong in
:class:`~harnesslab.telemetry.local_span_recorder.LocalSpanRecorder`;
this module covers operational narrative (startup, provider errors, migrations).

Configure via ``HARNESSLAB_LOG=DEBUG|INFO|WARNING|ERROR`` or CLI ``--log-level``.
Under pytest the default is ``WARNING`` unless ``HARNESSLAB_LOG`` is set explicitly.
"""

from __future__ import annotations

import logging
import os
import sys

_ROOT = "harnesslab"
_CONFIGURED = False

_NOISY_LOGGERS = ("httpx", "httpcore", "openai", "urllib3")


def configure_logging(level: str | None = None, *, force: bool = False) -> None:
    """Attach a stderr handler on the ``harnesslab`` logger tree."""

    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    numeric = _resolve_level(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )

    root = logging.getLogger(_ROOT)
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric)
    root.propagate = False

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(numeric, logging.WARNING))

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return ``harnesslab.<name>`` logger, configuring once on first use."""

    if not name.startswith(f"{_ROOT}."):
        name = f"{_ROOT}.{name}" if name != _ROOT else _ROOT
    configure_logging()
    return logging.getLogger(name)


def _resolve_level(level: str | None) -> int:
    raw = (level or os.environ.get("HARNESSLAB_LOG") or _default_level_name()).upper()
    return getattr(logging, raw, logging.INFO)


def _default_level_name() -> str:
    if _running_under_pytest():
        return "WARNING"
    return "INFO"


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules
