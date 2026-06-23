"""Offline tests for `harnesslab tune-prompt` (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesslab import cli
from harnesslab.core.models import Decision
from harnesslab.tune.prompt.candidate import PromptCandidate, freeze_candidates


def _write_candidates(path: Path) -> Path:
    return freeze_candidates(
        [PromptCandidate.from_text("GOOD: answer 42", label="g", source="model")],
        path,
    )


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["harnesslab", "tune-prompt", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return int(exc.value.code)


class _FinalModel:
    """Always answers '42' — passes some default-suite checks, not others."""

    def decide(self, session, user_input):  # noqa: ANN001, ANN201
        return Decision(kind="final", assistant_message="42")


def test_missing_candidates_file_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code = _run(monkeypatch, ["--candidates", str(tmp_path / "nope.json")])
    assert code == cli.EXIT_USAGE


def test_no_source_is_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    code = _run(monkeypatch, ["--model", "deepseek"])
    assert code == cli.EXIT_USAGE


def test_both_sources_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    code = _run(
        monkeypatch,
        ["--candidates", str(path), "--generate", "be concise"],
    )
    assert code == cli.EXIT_USAGE


def test_empty_candidates_file_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    code = _run(monkeypatch, ["--candidates", str(path)])
    assert code == cli.EXIT_USAGE


def test_simple_backend_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    code = _run(monkeypatch, ["--candidates", str(path), "--model", "simple"])
    assert code == cli.EXIT_USAGE


def test_judge_simple_backend_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _FinalModel())
    code = _run(
        monkeypatch,
        ["--candidates", str(path), "--model", "deepseek", "--judge-model", "simple"],
    )
    assert code == cli.EXIT_USAGE


def test_md_path_writes_proposal_with_fake_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    out = tmp_path / "props"

    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _FinalModel())

    code = _run(
        monkeypatch,
        ["--candidates", str(path), "--model", "deepseek", "--out", str(out)],
    )
    stdout = capsys.readouterr().out
    assert code == cli.EXIT_OK
    files = sorted(out.glob("prompt_*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "kind: prompt_tuning" in body
    assert "wrote " in stdout


def test_task_filter_limits_benchmark_tasks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _FinalModel())
    code = _run(
        monkeypatch,
        [
            "--candidates",
            str(path),
            "--model",
            "deepseek",
            "--task",
            "exact_token",
            "--format",
            "json",
        ],
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert payload["benchmark_tasks"] == 1


def test_task_filter_unknown_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _FinalModel())
    code = _run(
        monkeypatch,
        [
            "--candidates",
            str(path),
            "--model",
            "deepseek",
            "--task",
            "does_not_exist",
        ],
    )
    assert code == cli.EXIT_USAGE


def test_custom_benchmark_dir_is_loaded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    out = tmp_path / "props"
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "only.yaml").write_text(
        "input: solve\nchecks:\n  - kind: contains\n    value: '42'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _FinalModel())

    code = _run(
        monkeypatch,
        [
            "--candidates",
            str(path),
            "--model",
            "deepseek",
            "--benchmark-dir",
            str(bench),
            "--out",
            str(out),
            "--format",
            "json",
        ],
    )
    stdout = capsys.readouterr().out
    assert code == cli.EXIT_OK
    payload = json.loads(stdout)
    # Single-task suite with one trivially-passing check.
    assert payload["benchmark_tasks"] == 1


def test_json_path_does_not_touch_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    out = tmp_path / "props"

    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _FinalModel())

    code = _run(
        monkeypatch,
        [
            "--candidates",
            str(path),
            "--model",
            "deepseek",
            "--out",
            str(out),
            "--format",
            "json",
        ],
    )
    stdout = capsys.readouterr().out
    assert code == cli.EXIT_OK
    payload = json.loads(stdout)
    assert payload["kind"] == "prompt_tuning"
    assert not out.exists()


def test_generate_flow_freezes_candidates_and_writes_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "props"

    class _DualModel:
        """Generates a JSON array for the meta-prompt; answers '42' otherwise."""

        def decide(self, session, user_input):  # noqa: ANN001, ANN201
            staged = session.messages[-1].content if session.messages else user_input
            if "JSON array" in staged:
                return Decision(
                    kind="final",
                    assistant_message='["GOOD: answer 42", "ALT: be terse"]',
                )
            return Decision(kind="final", assistant_message="42")

    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _DualModel())

    code = _run(
        monkeypatch,
        [
            "--generate",
            "make the agent more concise",
            "--n",
            "2",
            "--model",
            "deepseek",
            "--out",
            str(out),
        ],
    )
    stdout = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "generated 2 candidate(s)" in stdout
    assert (out / "prompt_candidates.json").exists()
    assert len(sorted(out.glob("prompt_*.md"))) == 1
