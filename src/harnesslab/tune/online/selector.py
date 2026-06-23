"""Thompson sampling over Beta-Binomial success-rate posteriors."""

from __future__ import annotations

import random
from collections.abc import Callable

from harnesslab.improve.scoring import empirical_bayes_prior
from harnesslab.tune.online.models import ArmStats, OnlineArm, SelectionResult
from harnesslab.tune.online.store import OnlineSelectionStore

BetaSampler = Callable[[float, float], float]


def _default_sampler(alpha: float, beta: float) -> float:
    return random.betavariate(max(alpha, 1e-6), max(beta, 1e-6))


def thompson_select(
    arms: list[OnlineArm],
    store: OnlineSelectionStore,
    *,
    stats: dict[str, ArmStats] | None = None,
    prior_strength: float = 2.0,
    rng: BetaSampler | None = None,
) -> SelectionResult:
    """Pick the arm with the highest Beta posterior sample."""

    if not arms:
        raise ValueError("cannot select from an empty arm pool")
    if len(arms) == 1:
        arm = arms[0]
        st = (stats or store.load_stats()).get(arm.id, ArmStats())
        return SelectionResult(
            arm=arm,
            sample=1.0,
            successes=st.successes,
            trials=st.trials,
            candidates=[arm.id],
        )

    stats = stats if stats is not None else store.load_stats()
    total_successes = sum(stats.get(a.id, ArmStats()).successes for a in arms)
    total_trials = sum(stats.get(a.id, ArmStats()).trials for a in arms)
    alpha0, beta0 = empirical_bayes_prior(
        total_successes, total_trials, strength=prior_strength
    )

    sampler = rng or _default_sampler
    best: SelectionResult | None = None
    for arm in arms:
        st = stats.get(arm.id, ArmStats())
        alpha = alpha0 + st.successes
        beta = beta0 + max(st.trials - st.successes, 0)
        sample = sampler(alpha, beta)
        candidate = SelectionResult(
            arm=arm,
            sample=sample,
            successes=st.successes,
            trials=st.trials,
            candidates=[a.id for a in arms],
        )
        if best is None or sample > best.sample or (
            sample == best.sample and arm.id < best.arm.id
        ):
            best = candidate
    assert best is not None
    return best
