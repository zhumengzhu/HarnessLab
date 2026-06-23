"""Online Bayesian arm selection (Layer C).

Thompson sampling over **accepted** prompt-tuning arms on the ``run`` path only.
Default OFF; never wired into ``eval`` / ``replay``. Selections and outcomes are
persisted locally and recorded as span events when a recorder is available.

See ``docs/research/bayesian-self-evolution.md`` §4 Layer C.
"""

from harnesslab.tune.online.coordinator import OnlineSelectionCoordinator
from harnesslab.tune.online.feedback import session_outcome_success
from harnesslab.tune.online.loader import load_online_arms
from harnesslab.tune.online.models import ArmStats, OnlineArm, SelectionResult
from harnesslab.tune.online.selector import thompson_select
from harnesslab.tune.online.store import OnlineSelectionStore

__all__ = [
    "ArmStats",
    "OnlineArm",
    "OnlineSelectionCoordinator",
    "OnlineSelectionStore",
    "SelectionResult",
    "load_online_arms",
    "session_outcome_success",
    "thompson_select",
]
