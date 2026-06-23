"""Prompt tuning (Bayesian self-evolution Layer B2).

LLM-generated candidate **prompts** are scored by a *live-model* benchmark and
ranked by a Beta-Binomial success-rate posterior; the best candidate becomes an
advisory ``prompt_tuning`` proposal. This is the one place the project permits
an LLM to generate proposal content — see AGENTS.md "Proposal Handling" §5
amendment. The guarantees that make it safe:

- **Generation / scoring separation.** Candidates are produced offline (by any
  means, including an LLM) and **frozen** into a serialized artifact before
  they are scored. The frozen file is the boundary.
- **Isolation from eval/replay.** Scoring uses a live-model benchmark (with a
  prompt-quality suite that is completely separate from the eval ``Task``
  contract), so it never makes the deterministic paths non-deterministic.
- **Advisory only.** The output is a proposal a human reviews and accepts; it
  is never applied automatically.

See ``docs/research/bayesian-self-evolution.md`` §4 Layer B.
"""

from harnesslab.tune.prompt.benchmark import (
    BenchmarkResult,
    ModelFactory,
    PromptBenchmark,
)
from harnesslab.tune.prompt.candidate import (
    CandidateGenerator,
    ModelCandidateGenerator,
    PromptCandidate,
    StaticCandidateGenerator,
    baseline_candidate,
    default_system_prompt,
    freeze_candidates,
    generation_composer,
    load_candidates,
    make_model_text_generator,
)
from harnesslab.tune.prompt.judge import Judge, make_model_judge
from harnesslab.tune.prompt.pipeline import run_prompt_tuning
from harnesslab.tune.prompt.report import (
    PromptTuneReport,
    build_prompt_report,
    render_prompt_report,
    write_prompt_report,
)
from harnesslab.tune.prompt.selection import CandidateRanking, rank_candidates
from harnesslab.tune.prompt.suite import (
    DEFAULT_BENCHMARK_SUITE,
    PromptBenchmarkSuite,
    PromptBenchmarkTask,
    PromptCheck,
    bundled_benchmarks_dir,
    filter_benchmark_tasks,
    load_benchmark_suite,
    score_reply,
)

__all__ = [
    "DEFAULT_BENCHMARK_SUITE",
    "BenchmarkResult",
    "CandidateGenerator",
    "CandidateRanking",
    "Judge",
    "ModelCandidateGenerator",
    "ModelFactory",
    "PromptBenchmark",
    "PromptBenchmarkSuite",
    "PromptBenchmarkTask",
    "PromptCandidate",
    "PromptCheck",
    "PromptTuneReport",
    "StaticCandidateGenerator",
    "baseline_candidate",
    "build_prompt_report",
    "bundled_benchmarks_dir",
    "default_system_prompt",
    "filter_benchmark_tasks",
    "freeze_candidates",
    "generation_composer",
    "load_benchmark_suite",
    "load_candidates",
    "make_model_judge",
    "make_model_text_generator",
    "rank_candidates",
    "render_prompt_report",
    "run_prompt_tuning",
    "score_reply",
    "write_prompt_report",
]
