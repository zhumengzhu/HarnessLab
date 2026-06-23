"""Prompt-quality benchmark suite (decoupled from eval).

The eval ``Task`` model is built for deterministic replay and its
``final_reply_contains`` is the only live-usable signal. Prompt tuning needs a
benchmark whose pass/fail actually tracks *prompt quality* — instruction
following, conciseness, format adherence — scored against a live model. This
module defines that benchmark independently of ``eval`` so the two never
couple, and ships a bundled default suite that discriminates terse,
instruction-following prompts from verbose ones.

Scoring is intentionally **binary per task** (all checks must pass) so it feeds
the Beta-Binomial success-rate posterior in ``selection.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from harnesslab.tune.prompt.judge import Judge

CheckKind = Literal[
    "contains",
    "not_contains",
    "regex",
    "iregex",
    "equals",
    "max_chars",
    "judge",
]


class PromptCheck(BaseModel):
    """One assertion against a model's final reply.

    - ``contains`` / ``not_contains``: substring presence / absence (``value``)
    - ``regex`` / ``iregex``: (case-insensitive) ``re.search`` of ``value``
    - ``equals``: normalized equality (strip, drop surrounding quotes/punct,
      casefold) against ``value`` — penalizes preamble/verbosity
    - ``max_chars``: ``len(reply.strip()) <= limit`` — rewards conciseness
    - ``judge``: an injected ``Judge`` grades ``reply`` against ``value`` (rubric)
    """

    kind: CheckKind
    value: str = ""
    limit: int | None = None


class PromptBenchmarkTask(BaseModel):
    id: str
    input: str
    checks: list[PromptCheck] = Field(default_factory=list)
    max_steps: int = 3


class PromptBenchmarkSuite(BaseModel):
    tasks: list[PromptBenchmarkTask] = Field(default_factory=list)


class JudgeRequiredError(ValueError):
    """A task declares a ``judge`` check but no judge was provided."""


def _normalize(text: str) -> str:
    return text.strip().strip("\"'.!?").strip().casefold()


def check_passes(
    check: PromptCheck,
    *,
    task_input: str,
    reply: str,
    judge: Judge | None,
) -> bool:
    kind = check.kind
    if kind == "contains":
        return check.value in reply
    if kind == "not_contains":
        return check.value not in reply
    if kind == "regex":
        return re.search(check.value, reply) is not None
    if kind == "iregex":
        return re.search(check.value, reply, re.IGNORECASE) is not None
    if kind == "equals":
        return _normalize(reply) == _normalize(check.value)
    if kind == "max_chars":
        limit = check.limit if check.limit is not None else 0
        return len(reply.strip()) <= limit
    if kind == "judge":
        if judge is None:
            raise JudgeRequiredError(
                "a judge check requires a judge (pass --judge-model)"
            )
        return judge(task_input, check.value, reply)
    raise ValueError(f"unknown check kind: {kind!r}")


def score_reply(
    task: PromptBenchmarkTask, reply: str, *, judge: Judge | None = None
) -> bool:
    """A task passes iff every check passes."""

    return all(
        check_passes(c, task_input=task.input, reply=reply, judge=judge)
        for c in task.checks
    )


def load_benchmark_suite(path: Path) -> PromptBenchmarkSuite:
    """Load a suite from a single YAML file or a directory of ``*.yaml`` tasks.

    A file may contain either a full suite (``{"tasks": [...]}``) or a single
    task object. A directory loads every ``*.yaml`` as one task, sorted by name.
    """

    if path.is_dir():
        tasks: list[PromptBenchmarkTask] = []
        for entry in sorted(path.glob("*.yaml")):
            data = yaml.safe_load(entry.read_text(encoding="utf-8")) or {}
            tasks.append(_task_from_data(data, default_id=entry.stem))
        return PromptBenchmarkSuite(tasks=tasks)

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, dict) and "tasks" in data:
        return PromptBenchmarkSuite.model_validate(data)
    return PromptBenchmarkSuite(tasks=[_task_from_data(data, default_id=path.stem)])


def _task_from_data(data: dict, *, default_id: str) -> PromptBenchmarkTask:
    payload = dict(data)
    payload.setdefault("id", default_id)
    return PromptBenchmarkTask.model_validate(payload)


# A small, dependency-free default suite. Every task is single-turn and
# tool-free (cheap), and each is built so a terse, instruction-following prompt
# passes while a verbose / preamble-heavy prompt fails — giving the ranking
# real signal without any user setup.
DEFAULT_BENCHMARK_SUITE = PromptBenchmarkSuite(
    tasks=[
        PromptBenchmarkTask(
            id="number_only",
            input="What is 7 times 6? Reply with only the number, nothing else.",
            checks=[
                PromptCheck(kind="contains", value="42"),
                PromptCheck(kind="max_chars", limit=8),
            ],
        ),
        PromptBenchmarkTask(
            id="exact_token",
            input="Output exactly this and nothing else: ACK",
            checks=[PromptCheck(kind="equals", value="ACK")],
        ),
        PromptBenchmarkTask(
            id="single_word_done",
            input="Reply with the single word DONE.",
            checks=[PromptCheck(kind="equals", value="DONE")],
        ),
        PromptBenchmarkTask(
            id="capital_one_word",
            input="What is the capital of France? Answer in one word only.",
            checks=[
                PromptCheck(kind="iregex", value=r"\bparis\b"),
                PromptCheck(kind="not_contains", value="capital"),
                PromptCheck(kind="max_chars", limit=12),
            ],
        ),
        PromptBenchmarkTask(
            id="json_status_ok",
            input=(
                'Return a compact JSON object with a single key "status" '
                'whose value is "ok". No prose, no code fence.'
            ),
            checks=[
                PromptCheck(kind="regex", value=r'\{\s*"status"\s*:\s*"ok"\s*\}'),
                PromptCheck(kind="max_chars", limit=40),
            ],
        ),
    ]
)
