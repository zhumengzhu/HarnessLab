"""Offline tests for `harnesslab tune-prompt` (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesslab import cli
from harnesslab.core.models import Decision
from harnesslab.eval.task import Task, TaskExpected, TaskSuite, TaskTurn
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


def test_md_path_writes_proposal_with_fake_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    out = tmp_path / "props"

    class _FinalModel:
        def decide(self, session, user_input):  # noqa: ANN001, ANN201
            return Decision(kind="final", assistant_message="the answer is 42")

    def _fake_create_model(*_args, **_kwargs):  # noqa: ANN002, ANN003
        return _FinalModel()

    def _fake_suite(*_args, **_kwargs):  # noqa: ANN002, ANN003
        return TaskSuite(
            tasks=[
                Task(
                    name="solve",
                    goal="g",
                    turns=[TaskTurn(input="solve")],
                    expected=TaskExpected(final_reply_contains=["42"]),
                )
            ]
        )

    monkeypatch.setattr(cli, "create_model", _fake_create_model)
    monkeypatch.setattr(cli, "_load_suite_or_single", _fake_suite)

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


def test_json_path_does_not_touch_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_candidates(tmp_path / "cands.json")
    out = tmp_path / "props"

    class _FinalModel:
        def decide(self, session, user_input):  # noqa: ANN001, ANN201
            return Decision(kind="final", assistant_message="the answer is 42")

    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _FinalModel())
    monkeypatch.setattr(
        cli,
        "_load_suite_or_single",
        lambda *a, **k: TaskSuite(
            tasks=[
                Task(
                    name="solve",
                    goal="g",
                    turns=[TaskTurn(input="solve")],
                    expected=TaskExpected(final_reply_contains=["42"]),
                )
            ]
        ),
    )

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
            return Decision(kind="final", assistant_message="the answer is 42")

    monkeypatch.setattr(cli, "create_model", lambda *a, **k: _DualModel())
    monkeypatch.setattr(
        cli,
        "_load_suite_or_single",
        lambda *a, **k: TaskSuite(
            tasks=[
                Task(
                    name="solve",
                    goal="g",
                    turns=[TaskTurn(input="solve")],
                    expected=TaskExpected(final_reply_contains=["42"]),
                )
            ]
        ),
    )

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
