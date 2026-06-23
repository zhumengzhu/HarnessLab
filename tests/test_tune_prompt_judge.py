"""make_model_judge wraps a ModelPort as a PASS/FAIL judge (offline fake)."""

from __future__ import annotations

from harnesslab.core.models import Decision
from harnesslab.tune.prompt.judge import make_model_judge


class _VerdictModel:
    def __init__(self, verdict: str) -> None:
        self._verdict = verdict
        self.last_prompt = ""

    def decide(self, session, user_input):  # noqa: ANN001
        self.last_prompt = user_input
        return Decision(kind="final", assistant_message=self._verdict)


def test_pass_verdict_is_true() -> None:
    judge = make_model_judge(_VerdictModel("PASS"))
    assert judge("q", "be terse", "ok") is True


def test_non_pass_verdict_is_false() -> None:
    judge = make_model_judge(_VerdictModel("FAIL: too verbose"))
    assert judge("q", "be terse", "blah blah") is False


def test_prompt_includes_rubric_and_reply() -> None:
    model = _VerdictModel("PASS")
    judge = make_model_judge(model)
    judge("the question", "RUBRIC-TEXT", "REPLY-TEXT")
    assert "RUBRIC-TEXT" in model.last_prompt
    assert "REPLY-TEXT" in model.last_prompt
    assert "the question" in model.last_prompt
