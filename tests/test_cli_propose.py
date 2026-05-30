"""Tests for `harnesslab propose`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from harnesslab import cli

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_failure_spans.jsonl"


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _staged_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "spans.jsonl"
    shutil.copy(FIXTURE, target)
    return target


# ---------- usage / errors ----------


def test_propose_requires_at_least_one_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["harnesslab", "propose"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == cli.EXIT_USAGE
    assert "requires at least one of --trace or --eval-report" in err


def test_propose_missing_trace_file_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["harnesslab", "propose", "--trace", str(tmp_path / "missing.jsonl")],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "spans file not found" in str(exc.value)


def test_propose_missing_eval_report_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "propose",
            "--eval-report",
            str(tmp_path / "missing.json"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "eval report not found" in str(exc.value)


# ---------- markdown happy path ----------


def test_propose_md_writes_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = _staged_fixture(tmp_path)
    out = tmp_path / "props"
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "propose",
            "--trace",
            str(trace),
            "--out",
            str(out),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    stdout = capsys.readouterr().out

    assert exc.value.code == cli.EXIT_OK
    files = sorted(out.glob("prop_*.md"))
    assert len(files) == 2
    assert "wrote " in stdout
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert "status: open" in text
        assert "## Acceptance checklist" in text
        assert "uv run harnesslab eval" in text


def test_propose_md_is_idempotent_across_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A second run on the same trace must not duplicate proposals."""
    trace = _staged_fixture(tmp_path)
    out = tmp_path / "props"

    monkeypatch.setattr(
        "sys.argv", ["harnesslab", "propose", "--trace", str(trace), "--out", str(out)]
    )
    with pytest.raises(SystemExit) as exc1:
        cli.main()
    capsys.readouterr()
    assert exc1.value.code == cli.EXIT_OK
    first_run = sorted(out.glob("prop_*.md"))
    assert len(first_run) == 2

    # Same arguments, second run.
    with pytest.raises(SystemExit) as exc2:
        cli.main()
    out2 = capsys.readouterr().out
    assert exc2.value.code == cli.EXIT_OK
    assert "no new proposals" in out2
    second_run = sorted(out.glob("prop_*.md"))
    assert second_run == first_run  # nothing added, nothing renamed


# ---------- min-occurrences threshold ----------


def test_propose_threshold_above_fixture_yields_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = _staged_fixture(tmp_path)
    out = tmp_path / "props"
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "propose",
            "--trace",
            str(trace),
            "--out",
            str(out),
            "--min-occurrences",
            "3",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    stdout = capsys.readouterr().out

    assert exc.value.code == cli.EXIT_OK
    assert "no new proposals" in stdout
    assert not out.exists() or not any(out.glob("prop_*.md"))


# ---------- json format ----------


def test_propose_json_does_not_touch_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = _staged_fixture(tmp_path)
    out = tmp_path / "props"
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "propose",
            "--trace",
            str(trace),
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
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert {p["kind"] for p in payload} == {"policy_denial", "invalid_args"}
    # JSON mode is non-destructive: no files were written.
    assert not out.exists()


# ---------- eval-report path ----------


def test_propose_from_eval_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: feed a synthetic eval report into propose."""
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "task_name": "demo_task",
                        "passed": False,
                        "failures": ["bad thing", "bad thing"],
                        "metrics": {
                            "turns": 1,
                            "tool_calls": 0,
                            "tool_failures": 0,
                            "denials": 0,
                            "invalid_args": 0,
                        },
                        "final_reply": "",
                    }
                ],
                "regressions": [],
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "props"
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "propose",
            "--eval-report",
            str(report),
            "--out",
            str(out),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    capsys.readouterr()
    files = sorted(out.glob("prop_*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "kind: eval_regression" in body
    assert "demo_task" in body
