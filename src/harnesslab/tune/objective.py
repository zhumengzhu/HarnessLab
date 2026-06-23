"""Score a candidate runtime config by running the deterministic eval suite.

The objective is a weighted **cost** (lower is better): failing a task is the
dominant term, followed by tool failures / invalid args / denials, with a tiny
regularizer on total tool calls so ties break toward leaner runs. Because the
eval models are deterministic, ``score_config`` is a pure function of
``(suite, config)`` — running it twice yields an identical cost.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from harnesslab.core.config import RuntimeLimits
from harnesslab.eval.runner import TaskRunner
from harnesslab.eval.task import TaskResult, TaskSuite
from harnesslab.tune.space import Config, _to_runtime_limits_keys

# Cost weights. Failing a task dominates; efficiency terms break ties.
_W_FAILED_TASK = 100.0
_W_TOOL_FAILURE = 5.0
_W_INVALID_ARGS = 5.0
_W_DENIAL = 1.0
_W_TOOL_CALL = 0.1


@dataclass(frozen=True)
class ScoreBreakdown:
    cost: float
    failed_tasks: int
    tool_failures: int
    invalid_args: int
    denials: int
    tool_calls: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "cost": self.cost,
            "failed_tasks": self.failed_tasks,
            "tool_failures": self.tool_failures,
            "invalid_args": self.invalid_args,
            "denials": self.denials,
            "tool_calls": self.tool_calls,
        }


def _runtime_limits_for(config: Config) -> RuntimeLimits:
    return replace(RuntimeLimits(), **_to_runtime_limits_keys(config))


def _cost_from_results(results: list[TaskResult]) -> ScoreBreakdown:
    failed = sum(1 for r in results if not r.passed)
    tool_failures = sum(r.metrics.tool_failures for r in results)
    invalid_args = sum(r.metrics.invalid_args for r in results)
    denials = sum(r.metrics.denials for r in results)
    tool_calls = sum(r.metrics.tool_calls for r in results)
    cost = (
        _W_FAILED_TASK * failed
        + _W_TOOL_FAILURE * tool_failures
        + _W_INVALID_ARGS * invalid_args
        + _W_DENIAL * denials
        + _W_TOOL_CALL * tool_calls
    )
    return ScoreBreakdown(
        cost=cost,
        failed_tasks=failed,
        tool_failures=tool_failures,
        invalid_args=invalid_args,
        denials=denials,
        tool_calls=tool_calls,
    )


def score_config(suite: TaskSuite, config: Config) -> ScoreBreakdown:
    """Run ``suite`` under ``config`` and return the weighted cost breakdown."""

    runner = TaskRunner(
        base_limits=_runtime_limits_for(config),
        shell_profile=str(config.get("shell_profile", "dev")),
    )
    results = runner.run(suite)
    return _cost_from_results(results)


class EvalObjective:
    """Callable objective binding a fixed suite; caches identical configs.

    The cache makes the optimizer cheap when it revisits a config and keeps
    repeated tuner runs fast; it does not affect determinism.
    """

    def __init__(self, suite: TaskSuite) -> None:
        self._suite = suite
        self._cache: dict[tuple[tuple[str, object], ...], ScoreBreakdown] = {}

    def breakdown(self, config: Config) -> ScoreBreakdown:
        key = tuple(sorted(config.items()))
        cached = self._cache.get(key)
        if cached is None:
            cached = score_config(self._suite, config)
            self._cache[key] = cached
        return cached

    def __call__(self, config: Config) -> float:
        return self.breakdown(config).cost
