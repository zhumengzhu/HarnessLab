"""Prompt tuning (Bayesian self-evolution Layer B2).

LLM-generated candidate **prompts** are scored by a *live-model* benchmark and
ranked by a Beta-Binomial success-rate posterior; the best candidate becomes an
advisory ``prompt_tuning`` proposal. This is the one place the project permits
an LLM to generate proposal content — see AGENTS.md "Proposal Handling" §5
amendment. The guarantees that make it safe:

- **Generation / scoring separation.** Candidates are produced offline (by any
  means, including an LLM) and **frozen** into a serialized artifact before
  they are scored. The frozen file is the boundary.
- **Isolation from eval/replay.** Scoring uses a live-model benchmark that is
  completely separate from the deterministic ``eval`` / ``replay`` paths, so it
  never makes them non-deterministic.
- **Advisory only.** The output is a proposal a human reviews and accepts; it
  is never applied automatically.

See ``docs/research/bayesian-self-evolution.md`` §4 Layer B.
"""

from harnesslab.tune.prompt.benchmark import (
    BenchmarkResult,
    ModelFactory,
    PromptBenchmark,
    passes_task,
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
from harnesslab.tune.prompt.pipeline import run_prompt_tuning
from harnesslab.tune.prompt.report import (
    PromptTuneReport,
    build_prompt_report,
    render_prompt_report,
    write_prompt_report,
)
from harnesslab.tune.prompt.selection import CandidateRanking, rank_candidates

__all__ = [
    "BenchmarkResult",
    "CandidateGenerator",
    "CandidateRanking",
    "ModelCandidateGenerator",
    "ModelFactory",
    "PromptBenchmark",
    "PromptCandidate",
    "PromptTuneReport",
    "StaticCandidateGenerator",
    "baseline_candidate",
    "build_prompt_report",
    "default_system_prompt",
    "freeze_candidates",
    "generation_composer",
    "load_candidates",
    "make_model_text_generator",
    "passes_task",
    "rank_candidates",
    "render_prompt_report",
    "run_prompt_tuning",
    "write_prompt_report",
]
