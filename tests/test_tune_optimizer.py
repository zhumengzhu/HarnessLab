"""Tests for the deterministic GP-BO loop (Layer B1)."""

from __future__ import annotations

from harnesslab.tune.optimizer import optimize
from harnesslab.tune.space import CategoricalDim, IntDim, SearchSpace

# A convex parabola in the integer knob with its minimum at level 8; the
# categorical knob is irrelevant to the cost.
_LEVELS = (2, 4, 6, 8, 10)
_TARGET = 8


def _space() -> SearchSpace:
    return SearchSpace(
        [
            IntDim("knob", _LEVELS),
            CategoricalDim("flavour", ("a", "b")),
        ]
    )


def _cost(config: dict) -> float:
    return float((config["knob"] - _TARGET) ** 2)


def test_optimizer_finds_global_minimum() -> None:
    result = optimize(
        _space(),
        _cost,
        default_config={"knob": 2, "flavour": "a"},
        n_init=3,
        n_iter=8,
    )
    assert result.best_config["knob"] == _TARGET
    assert result.best_cost == 0.0


def test_optimizer_is_deterministic() -> None:
    kwargs = dict(default_config={"knob": 2, "flavour": "a"}, n_init=3, n_iter=6)
    a = optimize(_space(), _cost, **kwargs)
    b = optimize(_space(), _cost, **kwargs)
    assert a.best_config == b.best_config
    assert [c for c, _ in a.trials] == [c for c, _ in b.trials]


def test_optimizer_evaluates_default_first() -> None:
    result = optimize(
        _space(),
        _cost,
        default_config={"knob": 4, "flavour": "b"},
        n_init=2,
        n_iter=2,
    )
    first_config, _ = result.trials[0]
    assert first_config == {"knob": 4, "flavour": "b"}


def test_optimizer_never_exceeds_grid_size() -> None:
    space = _space()
    result = optimize(
        space,
        _cost,
        default_config={"knob": 2, "flavour": "a"},
        n_init=100,
        n_iter=100,
    )
    # No config is evaluated twice.
    seen = [tuple(sorted(c.items())) for c, _ in result.trials]
    assert len(seen) == len(set(seen))
    assert len(seen) <= space.size
