"""Rank prompt candidates by a Beta-Binomial success-rate posterior.

Reuses the Layer A estimator (``harnesslab.improve.scoring``). That estimator
is written for *failure* rates, but a Bernoulli rate is symmetric: feeding the
**pass count** as the numerator yields the posterior **success** rate. Ranking
by the lower credible bound (LCB) is conservative — a candidate that won 3/3 on
a tiny benchmark does not leapfrog one that won 90/100, because the LCB still
reflects the thinner evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from harnesslab.improve.scoring import empirical_bayes_prior, estimate_rate
from harnesslab.tune.prompt.benchmark import BenchmarkResult
from harnesslab.tune.prompt.candidate import PromptCandidate


@dataclass(frozen=True)
class CandidateRanking:
    candidate: PromptCandidate
    result: BenchmarkResult
    success_rate: float
    low: float
    high: float


def rank_candidates(
    scored: list[tuple[PromptCandidate, BenchmarkResult]],
    *,
    prior_strength: float = 2.0,
) -> list[CandidateRanking]:
    """Rank by descending success-rate LCB (ties broken by mean, then id)."""

    total_passes = sum(r.passes for _, r in scored)
    total_trials = sum(r.trials for _, r in scored)
    prior = empirical_bayes_prior(
        total_passes, total_trials, strength=prior_strength
    )

    rankings = [
        CandidateRanking(
            candidate=candidate,
            result=result,
            success_rate=(est := estimate_rate(result.passes, result.trials, prior=prior)).mean,
            low=est.low,
            high=est.high,
        )
        for candidate, result in scored
    ]
    rankings.sort(key=lambda r: (-r.low, -r.success_rate, r.candidate.id))
    return rankings
