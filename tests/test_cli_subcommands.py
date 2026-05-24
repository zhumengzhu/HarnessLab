"""Tests for the new harnesslab CLI subcommand surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesslab import cli
from harnesslab.eval.loader import load_suite


def _eval_task_count(repo_root: Path) -> int:
    return len(load_suite(repo_root / "eval" / "tasks").tasks)


@pytest.fixture()
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each CLI invocation in a clean cwd so eval/reports/ never pollutes."""

    monkeypatch.chdir(tmp_path)


# ---------- legacy-usage hint ----------


def test_legacy_invocation_prints_migration_hint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["harnesslab", "hello"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == cli.EXIT_USAGE
    assert "subcommands" in err
    assert "harnesslab run 'hello'" in err


def test_no_args_prints_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["harnesslab"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == cli.EXIT_USAGE
    assert "COMMAND" in err  # metavar present in help output


# ---------- harnesslab run ----------


def test_run_subcommand_prints_assistant_reply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "run",
            "hello",
            "--workspace-root",
            str(tmp_path),
            "--model",
            "simple",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "HarnessLab is ready" in out


def test_run_deepseek_without_api_key_returns_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "run",
            "hello",
            "--workspace-root",
            str(tmp_path),
            "--model",
            "deepseek",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == cli.EXIT_USAGE
    assert "DEEPSEEK_API_KEY is required" in err


# ---------- harnesslab eval ----------


def test_eval_subcommand_runs_all_tasks_and_passes(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "eval",
            "--tasks-dir",
            str(repo_root / "eval" / "tasks"),
            "--baseline",
            str(repo_root / "eval" / "baseline.json"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out

    assert exc.value.code == cli.EXIT_OK, out
    count = _eval_task_count(repo_root)
    assert f"Summary: {count}/{count} passed" in out
    report = (tmp_path / "reports" / "latest.json").read_text(encoding="utf-8")
    payload = json.loads(report)
    assert len(payload["results"]) == _eval_task_count(repo_root)
    assert payload["regressions"] == []


def test_eval_subcommand_single_task_via_stem(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "eval",
            "--tasks-dir",
            str(repo_root / "eval" / "tasks"),
            "--task",
            "01_assistant_fallback",
            "--baseline",
            str(repo_root / "eval" / "baseline.json"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK, out
    assert "1/1 passed" in out


def test_eval_subcommand_unknown_task_exits_with_message(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "eval",
            "--tasks-dir",
            str(repo_root / "eval" / "tasks"),
            "--task",
            "does_not_exist",
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    # SystemExit("...message...") yields the message as exc.code, not an int.
    assert "task file not found" in str(exc.value)


def test_eval_update_baseline_overwrites_file(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_path = tmp_path / "baseline.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "eval",
            "--tasks-dir",
            str(repo_root / "eval" / "tasks"),
            "--baseline",
            str(baseline_path),
            "--update-baseline",
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK
    assert "baseline updated" in out
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "results" in payload
    assert len(payload["results"]) == _eval_task_count(repo_root)


def test_eval_regression_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: plant a baseline that disagrees with the current run by
    pretending it previously had zero tool_failures; force a failing run by
    monkeypatching TaskRunner to return synthetic results."""
    from harnesslab.eval import task as task_mod

    fake_metrics = task_mod.TaskMetrics(
        turns=1, tool_calls=1, tool_failures=1, denials=0, invalid_args=0
    )
    fake_results = [
        task_mod.TaskResult(
            task_name="assistant_fallback",
            passed=False,
            failures=["synthetic failure"],
            metrics=fake_metrics,
            final_reply="",
        )
    ]
    monkeypatch.setattr(
        "harnesslab.cli.TaskRunner.run",
        lambda self, suite: fake_results,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "eval",
            "--tasks-dir",
            str(repo_root / "eval" / "tasks"),
            "--baseline",
            str(repo_root / "eval" / "baseline.json"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_REGRESSED, out
    assert "REGRESSIONS:" in out
    assert "task_now_failing" in out
