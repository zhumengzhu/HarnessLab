"""Tests for the live-model prompt benchmark (driven by a fake model)."""

from __future__ import annotations

import pytest

from harnesslab.core.models import Decision
from harnesslab.tune.prompt.benchmark import PromptBenchmark
from harnesslab.tune.prompt.candidate import PromptCandidate
from harnesslab.tune.prompt.suite import (
    PromptBenchmarkSuite,
    PromptBenchmarkTask,
    PromptCheck,
)


class _FinalModel:
    """Minimal ModelPort that always returns a fixed final reply."""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def decide(self, session, user_input: str) -> Decision:  # noqa: ANN001
        return Decision(kind="final", assistant_message=self._reply)


def _factory(candidate: PromptCandidate) -> _FinalModel:
    # A "good" (terse) prompt yields a short, on-target reply that passes both
    # the substring and the max_chars check; a "bad" prompt is verbose.
    reply = "42" if "GOOD" in candidate.system_prompt else "the answer is clearly 42"
    return _FinalModel(reply)


def _suite() -> PromptBenchmarkSuite:
    return PromptBenchmarkSuite(
        tasks=[
            PromptBenchmarkTask(
                id="solve",
                input="please solve",
                checks=[
                    PromptCheck(kind="contains", value="42"),
                    PromptCheck(kind="max_chars", limit=8),
                ],
            )
        ]
    )


def test_benchmark_distinguishes_good_and_bad_candidate() -> None:
    bench = PromptBenchmark(_suite(), _factory)
    good = bench.run(PromptCandidate.from_text("GOOD: answer tersely"))
    bad = bench.run(PromptCandidate.from_text("BAD verbose prompt"))
    assert good.passes == good.trials == 1
    assert bad.passes == 0
    assert bad.trials == 1


def test_repeats_multiply_trials() -> None:
    bench = PromptBenchmark(_suite(), _factory, repeats=3)
    result = bench.run(PromptCandidate.from_text("GOOD"))
    assert result.trials == 3
    assert result.passes == 3
    assert result.pass_rate == 1.0


def test_judge_check_is_invoked() -> None:
    suite = PromptBenchmarkSuite(
        tasks=[
            PromptBenchmarkTask(
                id="graded",
                input="q",
                checks=[PromptCheck(kind="judge", value="terse")],
            )
        ]
    )
    calls: list[str] = []

    def judge(task_input: str, rubric: str, reply: str) -> bool:
        calls.append(rubric)
        return "42" in reply

    bench = PromptBenchmark(suite, _factory, judge=judge)
    good = bench.run(PromptCandidate.from_text("GOOD"))
    assert good.passes == 1
    assert calls == ["terse"]


def test_repeats_must_be_positive() -> None:
    with pytest.raises(ValueError):
        PromptBenchmark(_suite(), _factory, repeats=0)
