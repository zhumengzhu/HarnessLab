"""Orchestrate the prompt-tuning pipeline: benchmark + rank + report.

This is the testable entry point used by the ``tune-prompt`` CLI. The baseline
candidate is always evaluated alongside the supplied (already frozen)
candidates so the report can state whether anything actually beat it.
"""

from __future__ import annotations

from datetime import datetime

from harnesslab.core.config import RuntimeLimits
from harnesslab.eval.task import TaskSuite
from harnesslab.tune.prompt.benchmark import ModelFactory, PromptBenchmark
from harnesslab.tune.prompt.candidate import PromptCandidate, baseline_candidate
from harnesslab.tune.prompt.report import PromptTuneReport, build_prompt_report
from harnesslab.tune.prompt.selection import rank_candidates


def run_prompt_tuning(
    *,
    candidates: list[PromptCandidate],
    suite: TaskSuite,
    model_factory: ModelFactory,
    instruction: str = "",
    repeats: int = 1,
    base_limits: RuntimeLimits | None = None,
    baseline: PromptCandidate | None = None,
    now: datetime | None = None,
) -> PromptTuneReport:
    baseline = baseline or baseline_candidate()

    pool: list[PromptCandidate] = []
    seen: set[str] = set()
    for cand in [baseline, *candidates]:
        if cand.id in seen:
            continue
        seen.add(cand.id)
        pool.append(cand)

    benchmark = PromptBenchmark(
        suite, model_factory, repeats=repeats, base_limits=base_limits
    )
    scored = [(cand, benchmark.run(cand)) for cand in pool]
    rankings = rank_candidates(scored)

    return build_prompt_report(
        rankings=rankings,
        baseline_id=baseline.id,
        instruction=instruction,
        repeats=repeats,
        benchmark_tasks=len(suite.tasks),
        now=now,
    )
