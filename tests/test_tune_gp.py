"""Tests for the GP surrogate + Expected Improvement (Layer B1)."""

from __future__ import annotations

from harnesslab.tune.gp import GaussianProcess, expected_improvement


def _fit_linear() -> GaussianProcess:
    # f(x) = 10*x over a 1-D normalized input.
    xs = [(0.0,), (0.25,), (0.5,), (0.75,), (1.0,)]
    ys = [10.0 * x[0] for x in xs]
    return GaussianProcess().fit(xs, ys)


def test_gp_interpolates_training_points() -> None:
    gp = _fit_linear()
    for x in ((0.0,), (0.5,), (1.0,)):
        mean, var = gp.predict(x)
        assert abs(mean - 10.0 * x[0]) < 1e-3
        assert var < 1e-3  # near-zero uncertainty at observed points


def test_gp_uncertainty_grows_away_from_data() -> None:
    gp = GaussianProcess().fit([(0.0,), (1.0,)], [0.0, 1.0])
    _, var_mid = gp.predict((0.5,))
    _, var_near = gp.predict((0.0,))
    assert var_mid > var_near


def test_gp_prediction_is_deterministic() -> None:
    a = _fit_linear().predict((0.6,))
    b = _fit_linear().predict((0.6,))
    assert a == b


def test_expected_improvement_zero_when_no_uncertainty() -> None:
    assert expected_improvement(mean=5.0, variance=0.0, best=10.0) == 0.0


def test_expected_improvement_positive_when_promising() -> None:
    # Candidate mean below incumbent best with real uncertainty -> EI > 0.
    ei = expected_improvement(mean=1.0, variance=1.0, best=5.0)
    assert ei > 0.0


def test_expected_improvement_minimization_prefers_lower_mean() -> None:
    low = expected_improvement(mean=1.0, variance=1.0, best=5.0)
    high = expected_improvement(mean=4.5, variance=1.0, best=5.0)
    assert low > high
