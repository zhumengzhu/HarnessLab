"""Smoke tests for `harnesslab tune`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesslab import cli

_TASKS_DIR = Path(__file__).resolve().parents[1] / "eval" / "tasks"


def test_tune_md_writes_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "props"
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "tune",
            "--tasks-dir",
            str(_TASKS_DIR),
            "--task",
            "01_assistant_fallback",
            "--n-init",
            "2",
            "--n-iter",
            "1",
            "--out",
            str(out),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    stdout = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK
    files = sorted(out.glob("tune_*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "kind: config_tuning" in body
    assert "## Suggested config diff (advisory; not auto-applied)" in body
    assert "wrote " in stdout


def test_tune_json_does_not_touch_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "props"
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "tune",
            "--tasks-dir",
            str(_TASKS_DIR),
            "--task",
            "01_assistant_fallback",
            "--n-init",
            "2",
            "--n-iter",
            "1",
            "--out",
            str(out),
            "--format",
            "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    stdout = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK
    payload = json.loads(stdout)
    assert payload["kind"] == "config_tuning"
    assert "best_config" in payload and "default_config" in payload
    assert not out.exists()
