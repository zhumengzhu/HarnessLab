"""Unit tests for the Beta-Binomial failure-rate estimator (Layer A).

See ``docs/research/bayesian-self-evolution.md`` §4 Layer A. The estimator is
a deterministic, dependency-free pure function; these tests pin its numerical
behaviour and the shrinkage / uncertainty properties the design relies on.
"""

from __future__ import annotations

from harnesslab.improve.scoring import (
    beta_ppf,
    empirical_bayes_prior,
    estimate_rate,
    regularized_incomplete_beta,
)

# ---------- regularized incomplete beta ----------


def test_incomplete_beta_uniform_special_case() -> None:
    # Beta(1, 1) is uniform: I_x(1, 1) == x.
    for x in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
        assert abs(regularized_incomplete_beta(1.0, 1.0, x) - x) < 1e-12


def test_incomplete_beta_is_monotonic_in_x() -> None:
    prev = -1.0
    for i in range(0, 101):
        x = i / 100.0
        val = regularized_incomplete_beta(2.0, 5.0, x)
        assert val >= prev
        prev = val


def test_incomplete_beta_clamps_outside_unit_interval() -> None:
    assert regularized_incomplete_beta(2.0, 3.0, -0.5) == 0.0
    assert regularized_incomplete_beta(2.0, 3.0, 1.5) == 1.0


# ---------- beta_ppf ----------


def test_beta_ppf_uniform_special_case() -> None:
    for p in (0.05, 0.5, 0.95):
        assert abs(beta_ppf(p, 1.0, 1.0) - p) < 1e-9


def test_beta_ppf_inverts_cdf() -> None:
    a, b = 3.0, 7.0
    for p in (0.05, 0.25, 0.5, 0.75, 0.95):
        x = beta_ppf(p, a, b)
        assert abs(regularized_incomplete_beta(a, b, x) - p) < 1e-6


def test_beta_ppf_clamps_extreme_probabilities() -> None:
    assert beta_ppf(0.0, 2.0, 2.0) == 0.0
    assert beta_ppf(1.0, 2.0, 2.0) == 1.0


# ---------- empirical_bayes_prior ----------


def test_prior_centres_on_global_base_rate() -> None:
    # Strength chosen so neither pseudo-count hits the 0.5 Jeffreys floor.
    alpha0, beta0 = empirical_bayes_prior(20, 100, strength=5.0)
    base = alpha0 / (alpha0 + beta0)
    assert abs(base - 0.2) < 1e-9


def test_prior_floor_keeps_parameters_proper_when_all_failures() -> None:
    # base rate == 1.0 must not collapse beta0 to zero.
    alpha0, beta0 = empirical_bayes_prior(5, 5)
    assert beta0 >= 0.5
    assert alpha0 > 0.0


def test_prior_handles_zero_trials() -> None:
    alpha0, beta0 = empirical_bayes_prior(0, 0)
    assert alpha0 > 0.0 and beta0 > 0.0


# ---------- estimate_rate ----------


def test_estimate_rate_mean_within_interval() -> None:
    est = estimate_rate(3, 10, prior=empirical_bayes_prior(3, 10))
    assert 0.0 <= est.low <= est.mean <= est.high <= 1.0


def test_estimate_rate_clamps_trials_below_failures() -> None:
    est = estimate_rate(5, 2, prior=(0.5, 0.5))
    assert est.trials == 5


def test_more_data_tightens_interval() -> None:
    prior = (0.5, 0.5)
    narrow = estimate_rate(50, 100, prior=prior)
    wide = estimate_rate(1, 2, prior=prior)
    assert (narrow.high - narrow.low) < (wide.high - wide.low)


def test_shrinkage_pulls_small_samples_toward_base_rate() -> None:
    # Global base rate is low; a single-ish high observed rate should be
    # pulled down relative to its naive 1.0 point estimate.
    prior = empirical_bayes_prior(total_failures=5, total_trials=100)
    est = estimate_rate(2, 2, prior=prior)
    assert est.mean < 1.0
    assert est.low < est.mean


def test_estimate_rate_is_deterministic() -> None:
    prior = empirical_bayes_prior(7, 50)
    a = estimate_rate(4, 20, prior=prior)
    b = estimate_rate(4, 20, prior=prior)
    assert a == b
