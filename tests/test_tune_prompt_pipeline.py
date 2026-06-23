"""End-to-end (offline) test of the prompt-tuning pipeline with a fake model."""

from __future__ import annotations

from harnesslab.core.models import Decision
from harnesslab.eval.task import Task, TaskExpected, TaskSuite, TaskTurn
from harnesslab.tune.prompt.candidate import PromptCandidate, baseline_candidate
from harnesslab.tune.prompt.pipeline import run_prompt_tuning


class _FinalModel:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def decide(self, session, user_input: str) -> Decision:  # noqa: ANN001
        return Decision(kind="final", assistant_message=self._reply)


def _factory(candidate: PromptCandidate) -> _FinalModel:
    reply = "the answer is 42" if "GOOD" in candidate.system_prompt else "no clue"
    return _FinalModel(reply)


def _suite() -> TaskSuite:
    return TaskSuite(
        tasks=[
            Task(
                name="solve",
                goal="solve it",
                turns=[TaskTurn(input="please solve")],
                expected=TaskExpected(final_reply_contains=["42"]),
            )
        ]
    )


def test_pipeline_picks_better_candidate_and_includes_baseline() -> None:
    good = PromptCandidate.from_text("GOOD: always answer 42")
    bad = PromptCandidate.from_text("BAD prompt")
    report = run_prompt_tuning(
        candidates=[good, bad],
        suite=_suite(),
        model_factory=_factory,
        instruction="improve accuracy",
        repeats=2,
    )
    assert report.improved
    assert report.best_id == good.id
    ranked_ids = {r.candidate_id for r in report.rankings}
    assert baseline_candidate().id in ranked_ids
    assert good.id in ranked_ids and bad.id in ranked_ids


def test_pipeline_dedupes_baseline_passed_as_candidate() -> None:
    base = baseline_candidate()
    report = run_prompt_tuning(
        candidates=[base],
        suite=_suite(),
        model_factory=_factory,
        repeats=1,
    )
    # baseline appears exactly once even though it was also passed as a candidate
    base_rows = [r for r in report.rankings if r.candidate_id == base.id]
    assert len(base_rows) == 1
