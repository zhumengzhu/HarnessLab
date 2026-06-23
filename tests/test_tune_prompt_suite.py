"""Unit tests for the prompt-quality benchmark suite + checks + scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from harnesslab.tune.prompt.suite import (
    DEFAULT_BENCHMARK_SUITE,
    JudgeRequiredError,
    PromptBenchmarkTask,
    PromptCheck,
    bundled_benchmarks_dir,
    check_passes,
    filter_benchmark_tasks,
    load_benchmark_suite,
    score_reply,
)


def _check(kind: str, **kw) -> PromptCheck:
    return PromptCheck(kind=kind, **kw)


def test_contains_and_not_contains() -> None:
    assert check_passes(
        _check("contains", value="42"), task_input="", reply="it is 42", judge=None
    )
    assert not check_passes(
        _check("contains", value="42"), task_input="", reply="nope", judge=None
    )
    assert check_passes(
        _check("not_contains", value="sorry"), task_input="", reply="42", judge=None
    )
    assert not check_passes(
        _check("not_contains", value="sorry"), task_input="", reply="sorry, no", judge=None
    )


def test_regex_variants() -> None:
    assert check_passes(
        _check("regex", value=r"\d+"), task_input="", reply="x42", judge=None
    )
    assert not check_passes(
        _check("regex", value=r"PARIS"), task_input="", reply="paris", judge=None
    )
    assert check_passes(
        _check("iregex", value=r"\bparis\b"), task_input="", reply="Paris", judge=None
    )


def test_equals_normalizes_punctuation_and_case() -> None:
    eq = _check("equals", value="DONE")
    assert check_passes(eq, task_input="", reply="done", judge=None)
    assert check_passes(eq, task_input="", reply="  DONE.  ", judge=None)
    assert not check_passes(eq, task_input="", reply="Sure, DONE", judge=None)


def test_max_chars_rewards_brevity() -> None:
    mc = _check("max_chars", limit=8)
    assert check_passes(mc, task_input="", reply="  42 ", judge=None)
    assert not check_passes(mc, task_input="", reply="the answer is 42", judge=None)


def test_judge_check_requires_judge() -> None:
    with pytest.raises(JudgeRequiredError):
        check_passes(
            _check("judge", value="must be polite"), task_input="hi", reply="x", judge=None
        )


def test_judge_check_uses_injected_judge() -> None:
    seen: dict[str, str] = {}

    def judge(task_input: str, rubric: str, reply: str) -> bool:
        seen["rubric"] = rubric
        return rubric in reply

    assert check_passes(
        _check("judge", value="POLITE"), task_input="hi", reply="POLITE answer", judge=judge
    )
    assert seen["rubric"] == "POLITE"


def test_score_reply_requires_all_checks() -> None:
    task = PromptBenchmarkTask(
        id="t",
        input="x",
        checks=[_check("contains", value="42"), _check("max_chars", limit=4)],
    )
    assert score_reply(task, "  42 ")
    assert not score_reply(task, "the answer is 42")  # too long
    assert not score_reply(task, "no")  # missing 42


def test_default_suite_is_non_empty() -> None:
    assert len(DEFAULT_BENCHMARK_SUITE.tasks) >= 6
    assert all(t.checks for t in DEFAULT_BENCHMARK_SUITE.tasks)


def test_filter_benchmark_tasks() -> None:
    suite = DEFAULT_BENCHMARK_SUITE
    filtered = filter_benchmark_tasks(suite, ["exact_token", "number_only"])
    assert [t.id for t in filtered.tasks] == ["number_only", "exact_token"]


def test_bundled_benchmarks_dir_has_examples() -> None:
    root = bundled_benchmarks_dir()
    assert (root / "minimal" / "terse_number.yaml").is_file()


def test_load_suite_from_full_file(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        "tasks:\n"
        "  - id: a\n"
        "    input: hi\n"
        "    checks:\n"
        "      - kind: contains\n"
        "        value: x\n",
        encoding="utf-8",
    )
    suite = load_benchmark_suite(path)
    assert [t.id for t in suite.tasks] == ["a"]
    assert suite.tasks[0].checks[0].kind == "contains"


def test_load_suite_from_directory(tmp_path: Path) -> None:
    (tmp_path / "one.yaml").write_text(
        "input: hi\nchecks:\n  - kind: contains\n    value: x\n", encoding="utf-8"
    )
    (tmp_path / "two.yaml").write_text(
        "input: yo\nchecks:\n  - kind: equals\n    value: y\n", encoding="utf-8"
    )
    suite = load_benchmark_suite(tmp_path)
    assert [t.id for t in suite.tasks] == ["one", "two"]
