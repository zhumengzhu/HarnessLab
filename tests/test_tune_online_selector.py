"""Thompson sampling selector."""

from __future__ import annotations

from harnesslab.tune.online.models import ArmStats, OnlineArm
from harnesslab.tune.online.selector import thompson_select
from harnesslab.tune.online.store import OnlineSelectionStore


def test_thompson_prefers_high_success_arm(tmp_path) -> None:
    store = OnlineSelectionStore(tmp_path / "stats.json")
    stats = {
        "good": ArmStats(successes=20, trials=20),
        "bad": ArmStats(successes=2, trials=20),
    }
    arms = [
        OnlineArm(id="good", system_prompt="G", source="config"),
        OnlineArm(id="bad", system_prompt="B", source="config"),
    ]
    samples = iter([0.9, 0.1])

    def rng(alpha: float, beta: float) -> float:
        return next(samples)

    result = thompson_select(arms, store, stats=stats, rng=rng)
    assert result.arm.id == "good"


def test_single_arm_short_circuit(tmp_path) -> None:
    store = OnlineSelectionStore(tmp_path / "stats.json")
    arms = [OnlineArm(id="only", system_prompt="x", source="baseline")]
    result = thompson_select(arms, store)
    assert result.arm.id == "only"
