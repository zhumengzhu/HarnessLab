"""Tests for the eval-suite objective (Layer B1)."""

from __future__ import annotations

from pathlib import Path

from harnesslab.eval.loader import load_task
from harnesslab.eval.task import TaskSuite
from harnesslab.tune.objective import EvalObjective, score_config
from harnesslab.tune.space import DEFAULT_CONFIG

_TASKS_DIR = Path(__file__).resolve().parents[1] / "eval" / "tasks"


def _single_task_suite() -> TaskSuite:
    task = load_task(_TASKS_DIR / "01_assistant_fallback.yaml")
    return TaskSuite(tasks=[task])


def test_score_config_returns_finite_cost_with_breakdown() -> None:
    suite = _single_task_suite()
    breakdown = score_config(suite, DEFAULT_CONFIG)
    assert breakdown.cost >= 0.0
    d = breakdown.as_dict()
    for key in ("cost", "failed_tasks", "tool_failures", "invalid_args", "denials", "tool_calls"):
        assert key in d


def test_score_config_is_deterministic() -> None:
    suite = _single_task_suite()
    a = score_config(suite, DEFAULT_CONFIG)
    b = score_config(suite, DEFAULT_CONFIG)
    assert a == b


def test_eval_objective_caches_repeated_configs() -> None:
    suite = _single_task_suite()
    objective = EvalObjective(suite)
    first = objective(DEFAULT_CONFIG)
    second = objective(DEFAULT_CONFIG)
    assert first == second
    # Cache hit returns the identical breakdown object.
    assert objective.breakdown(DEFAULT_CONFIG) is objective.breakdown(DEFAULT_CONFIG)
