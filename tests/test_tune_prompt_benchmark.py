"""Tests for the live-model prompt benchmark (driven by a fake model)."""

from __future__ import annotations

import pytest

from harnesslab.core.models import Decision
from harnesslab.eval.task import Task, TaskExpected, TaskSuite, TaskTurn
from harnesslab.tune.prompt.benchmark import PromptBenchmark, passes_task
from harnesslab.tune.prompt.candidate import PromptCandidate


class _FinalModel:
    """Minimal ModelPort that always returns a fixed final reply."""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def decide(self, session, user_input: str) -> Decision:  # noqa: ANN001
        return Decision(kind="final", assistant_message=self._reply)


def _factory(candidate: PromptCandidate) -> _FinalModel:
    reply = "the answer is 42" if "GOOD" in candidate.system_prompt else "no clue"
    return _FinalModel(reply)


def _suite(needle: str = "42") -> TaskSuite:
    task = Task(
        name="solve",
        goal="solve it",
        turns=[TaskTurn(input="please solve")],
        expected=TaskExpected(final_reply_contains=[needle]),
    )
    return TaskSuite(tasks=[task])


def test_passes_task_substring_only() -> None:
    task = _suite("42").tasks[0]
    assert passes_task(task, "the answer is 42")
    assert not passes_task(task, "no number here")


def test_benchmark_distinguishes_good_and_bad_candidate() -> None:
    bench = PromptBenchmark(_suite(), _factory)
    good = bench.run(PromptCandidate.from_text("GOOD: answer 42"))
    bad = bench.run(PromptCandidate.from_text("BAD prompt"))
    assert good.passes == good.trials == 1
    assert bad.passes == 0
    assert bad.trials == 1


def test_repeats_multiply_trials() -> None:
    bench = PromptBenchmark(_suite(), _factory, repeats=3)
    result = bench.run(PromptCandidate.from_text("GOOD"))
    assert result.trials == 3
    assert result.passes == 3
    assert result.pass_rate == 1.0


def test_repeats_must_be_positive() -> None:
    with pytest.raises(ValueError):
        PromptBenchmark(_suite(), _factory, repeats=0)
