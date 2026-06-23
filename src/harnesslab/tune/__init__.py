"""Bayesian configuration tuning (Layer B1).

Offline, deterministic Bayesian optimization over the runtime knob space
(``RuntimeLimits`` + shell profile), scored by the deterministic ``eval``
suite as utility. See ``docs/research/bayesian-self-evolution.md`` §4 Layer B.

This layer optimizes only knobs the *deterministic* eval models react to
(policy / limits / budget) — not prompt text or sampling params, which the
``SimpleModel`` / ``ReplayModel`` ignore. The optimizer uses no LLM and no
RNG, so it preserves the deterministic-artifact contract; its output is an
advisory config-diff proposal that a human reviews and accepts.

Public API:
    SearchSpace, IntDim, CategoricalDim, DEFAULT_SEARCH_SPACE
    EvalObjective, score_config
    GaussianProcess, expected_improvement
    optimize -> TuneReport
    TuneReport, TrialRecord, render_report
"""

from harnesslab.tune.gp import GaussianProcess, expected_improvement
from harnesslab.tune.objective import EvalObjective, ScoreBreakdown, score_config
from harnesslab.tune.optimizer import OptimizeResult, optimize
from harnesslab.tune.report import (
    TrialRecord,
    TuneReport,
    build_report,
    render_report,
    write_report,
)
from harnesslab.tune.space import (
    DEFAULT_CONFIG,
    DEFAULT_SEARCH_SPACE,
    CategoricalDim,
    IntDim,
    SearchSpace,
)

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_SEARCH_SPACE",
    "CategoricalDim",
    "EvalObjective",
    "GaussianProcess",
    "IntDim",
    "OptimizeResult",
    "ScoreBreakdown",
    "SearchSpace",
    "TrialRecord",
    "TuneReport",
    "build_report",
    "expected_improvement",
    "optimize",
    "render_report",
    "score_config",
    "write_report",
]
