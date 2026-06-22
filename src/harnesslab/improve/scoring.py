"""Beta-Binomial failure-rate estimation for the Improvement Loop.

Layer A of the Bayesian self-evolution design
(``docs/research/bayesian-self-evolution.md``). Replaces raw occurrence
counting with a posterior estimate of each cluster's failure rate, so a
high-rate failure on a rarely-invoked tool is not buried under a low-rate
failure on a heavily-used one, and a one-off spike is shrunk toward the
global base rate instead of over-firing.

Everything here is a **deterministic, closed-form** pure function of its
integer inputs (failures, trials). There is no sampling and no RNG, so the
estimator is safe to use on the deterministic ``eval`` / ``replay`` paths
(see the determinism contract in the design doc §6).

The credible interval uses the regularized incomplete beta function
``I_x(a, b)`` (Numerical Recipes continued-fraction form) inverted by
bisection — a self-contained implementation so the runtime keeps its
"no new dependency without clear need" discipline (no scipy/numpy).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Jeffreys-style floor so neither prior pseudo-count collapses to 0 when the
# observed base rate is exactly 0 or 1 (e.g. successes were never recorded).
_PRIOR_FLOOR = 0.5
_DEFAULT_PRIOR_STRENGTH = 2.0
_DEFAULT_CREDIBLE_MASS = 0.90


@dataclass(frozen=True)
class RateEstimate:
    """Posterior failure-rate estimate for one cluster."""

    failures: int
    trials: int
    mean: float
    low: float
    high: float


def empirical_bayes_prior(
    total_failures: int,
    total_trials: int,
    *,
    strength: float = _DEFAULT_PRIOR_STRENGTH,
) -> tuple[float, float]:
    """Return ``(alpha0, beta0)`` for a weak prior centred on the global rate.

    The prior is a Beta distribution whose mean is the global base failure
    rate and whose total pseudo-count is ``strength``. Sparse clusters shrink
    toward this base rate; high-volume clusters quickly overwhelm it.
    """

    base = total_failures / total_trials if total_trials > 0 else 0.5
    base = min(max(base, 1e-6), 1.0 - 1e-6)
    alpha0 = max(base * strength, _PRIOR_FLOOR)
    beta0 = max((1.0 - base) * strength, _PRIOR_FLOOR)
    return alpha0, beta0


def estimate_rate(
    failures: int,
    trials: int,
    *,
    prior: tuple[float, float],
    credible_mass: float = _DEFAULT_CREDIBLE_MASS,
) -> RateEstimate:
    """Posterior failure rate for ``failures`` out of ``trials`` under ``prior``.

    ``trials`` is clamped to be at least ``failures`` (a denominator can never
    be smaller than its numerator).
    """

    failures = max(failures, 0)
    trials = max(trials, failures)
    alpha0, beta0 = prior
    a = alpha0 + failures
    b = beta0 + (trials - failures)
    mean = a / (a + b)
    tail = (1.0 - credible_mass) / 2.0
    low = beta_ppf(tail, a, b)
    high = beta_ppf(1.0 - tail, a, b)
    return RateEstimate(failures=failures, trials=trials, mean=mean, low=low, high=high)


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function ``I_x(a, b)``."""

    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    # Use the continued fraction in its faster-converging half of the domain.
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_ppf(p: float, a: float, b: float) -> float:
    """Inverse CDF (quantile) of ``Beta(a, b)`` via bisection on ``I_x``."""

    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if regularized_incomplete_beta(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""

    max_iter = 300
    eps = 3.0e-16
    tiny = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h
