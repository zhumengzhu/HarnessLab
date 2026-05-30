"""CLI tests for harnesslab pricing subcommand."""

from __future__ import annotations

import subprocess
import sys


def test_cli_pricing_fingerprint() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "harnesslab.cli", "pricing", "fingerprint"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "fingerprint:" in proc.stdout


def test_cli_pricing_audit() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "harnesslab.cli", "pricing", "audit", "--currency", "USD"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode in {0, 2}
    assert "missing_model_ids:" in proc.stdout
