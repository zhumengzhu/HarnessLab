"""Optional LLM-judge scorer for prompt benchmarks.

A ``Judge`` decides, for one benchmark item, whether a reply satisfies a
free-text rubric. It is injectable so the benchmark is testable with a fake
judge (no network); ``make_model_judge`` wraps a real ``ModelPort`` as a judge
for the CLI ``--judge-model`` path.

The judge is non-deterministic and costs API calls, so it is opt-in: only
tasks that declare a ``judge`` check invoke it, and the default bundled suite
uses deterministic checks only.
"""

from __future__ import annotations

from collections.abc import Callable

from harnesslab.core.contracts import ModelPort
from harnesslab.core.models import Message, Session

# (task_input, rubric, reply) -> pass/fail
Judge = Callable[[str, str, str], bool]

_JUDGE_PROMPT = """\
You are grading an assistant's reply against a rubric. Be strict.

User request:
{task_input}

Rubric (the reply must satisfy this):
{rubric}

Assistant reply:
{reply}

Answer with exactly one word: PASS if the reply satisfies the rubric, or FAIL
if it does not.
"""


def make_model_judge(model: ModelPort) -> Judge:
    """Wrap a ``ModelPort`` as a ``Judge`` that returns True on a ``PASS`` verdict."""

    def judge(task_input: str, rubric: str, reply: str) -> bool:
        prompt = _JUDGE_PROMPT.format(
            task_input=task_input.strip(), rubric=rubric.strip(), reply=reply.strip()
        )
        session = Session(goal="prompt-benchmark-judge")
        session.messages.append(Message(role="user", content=prompt))
        decision = model.decide(session, prompt)
        verdict = (decision.assistant_message or "").strip().upper()
        return verdict.startswith("PASS")

    return judge
