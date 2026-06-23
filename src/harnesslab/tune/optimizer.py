"""Deterministic Gaussian-process Bayesian optimization over a SearchSpace.

The loop is fully deterministic (no RNG):

1. Evaluate the default config first (the incumbent baseline).
2. Fill an initial design by greedy max-min distance over the grid.
3. Fit the GP surrogate and pick the grid point with the highest Expected
   Improvement; repeat for ``n_iter`` rounds (or until EI vanishes / the grid
   is exhausted).

Ties (in distance or EI) are broken toward the lowest grid index, so repeated
runs produce identical trial sequences. ``cost_fn`` is treated as a black box;
the optimizer never inspects its internals, which keeps it trivially testable
with synthetic objectives.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from harnesslab.tune.gp import GaussianProcess, expected_improvement
from harnesslab.tune.space import Config, SearchSpace


@dataclass
class OptimizeResult:
    best_config: Config
    best_cost: float
    trials: list[tuple[Config, float]] = field(default_factory=list)


def _sqdist(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b, strict=True))


def _config_key(config: Config) -> tuple[tuple[str, object], ...]:
    return tuple(sorted(config.items()))


def optimize(
    space: SearchSpace,
    cost_fn: Callable[[Config], float],
    *,
    default_config: Config,
    n_init: int = 6,
    n_iter: int = 12,
) -> OptimizeResult:
    grid = space.grid()
    vectors = [space.encode(c) for c in grid]
    index_by_key = {_config_key(c): i for i, c in enumerate(grid)}

    costs: dict[int, float] = {}
    evaluated: list[int] = []
    trials: list[tuple[Config, float]] = []

    def evaluate(i: int) -> None:
        if i in costs:
            return
        value = cost_fn(grid[i])
        costs[i] = value
        evaluated.append(i)
        trials.append((dict(grid[i]), value))

    # 1. Baseline first (if it lies on the grid).
    default_idx = index_by_key.get(_config_key(space.clamp(default_config)))
    if default_idx is not None:
        evaluate(default_idx)

    # 2. Space-filling initial design via greedy max-min distance.
    target_init = min(n_init, len(grid))
    while len(evaluated) < target_init:
        best_i, best_d = None, -1.0
        for i in range(len(grid)):
            if i in costs:
                continue
            d = (
                min(_sqdist(vectors[i], vectors[j]) for j in evaluated)
                if evaluated
                else 1.0
            )
            if d > best_d:
                best_d, best_i = d, i
        if best_i is None:
            break
        evaluate(best_i)

    # 3. EI-driven Bayesian optimization.
    for _ in range(n_iter):
        if len(evaluated) >= len(grid):
            break
        x_obs = [vectors[i] for i in evaluated]
        y_obs = [costs[i] for i in evaluated]
        gp = GaussianProcess().fit(x_obs, y_obs)
        incumbent = min(y_obs)
        best_i, best_ei = None, -1.0
        for i in range(len(grid)):
            if i in costs:
                continue
            mean, var = gp.predict(vectors[i])
            ei = expected_improvement(mean, var, incumbent)
            if ei > best_ei:
                best_ei, best_i = ei, i
        if best_i is None or best_ei <= 1e-12:
            break
        evaluate(best_i)

    best_idx = min(costs, key=lambda i: (costs[i], i))
    return OptimizeResult(
        best_config=dict(grid[best_idx]),
        best_cost=costs[best_idx],
        trials=trials,
    )
