"""Orchestrate arm loading, Thompson selection, and outcome recording."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from harnesslab.core.contracts import SpanRecorderPort
from harnesslab.core.models import Session
from harnesslab.tune.online.feedback import session_outcome_success
from harnesslab.tune.online.loader import load_online_arms
from harnesslab.tune.online.models import ArmStats, OnlineArm, SelectionResult
from harnesslab.tune.online.selector import BetaSampler, thompson_select
from harnesslab.tune.online.store import DEFAULT_STORE_PATH, OnlineSelectionStore

BetaSamplerFactory = Callable[[], BetaSampler]


class OnlineSelectionCoordinator:
    """Run-path bandit coordinator (Layer C)."""

    def __init__(
        self,
        arms: list[OnlineArm],
        store: OnlineSelectionStore,
        *,
        rng: BetaSampler | None = None,
        spans: SpanRecorderPort | None = None,
    ) -> None:
        if not arms:
            raise ValueError("online selection requires at least one arm")
        self._arms = arms
        self._store = store
        self._rng = rng
        self._spans = spans
        self._last_selection: SelectionResult | None = None

    @classmethod
    def from_workspace(
        cls,
        workspace_root: Path,
        *,
        proposals_dir: Path | None = None,
        store_path: Path | None = None,
        spans: SpanRecorderPort | None = None,
        rng: BetaSampler | None = None,
    ) -> OnlineSelectionCoordinator:
        props = proposals_dir or (workspace_root / "proposals")
        store = OnlineSelectionStore(store_path or DEFAULT_STORE_PATH)
        arms = load_online_arms(proposals_dir=props, include_baseline=True)
        return cls(arms, store, rng=rng, spans=spans)

    @property
    def arms(self) -> list[OnlineArm]:
        return list(self._arms)

    @property
    def last_selection(self) -> SelectionResult | None:
        return self._last_selection

    def stats(self) -> dict[str, ArmStats]:
        return self._store.load_stats()

    def select(self) -> SelectionResult:
        result = thompson_select(self._arms, self._store, rng=self._rng)
        self._last_selection = result
        return result

    def record_session(self, session: Session) -> ArmStats | None:
        if self._last_selection is None:
            return None
        success = session_outcome_success(session)
        updated = self._store.record(self._last_selection.arm.id, success=success)
        return updated

    def emit_selection_span(self, turn_span_id: str) -> None:
        if self._spans is None or self._last_selection is None:
            return
        sel = self._last_selection
        self._spans.add_span_event(
            turn_span_id,
            "online_selection.selected",
            {
                "arm_id": sel.arm.id,
                "arm_source": sel.arm.source,
                "sample": sel.sample,
                "successes": sel.successes,
                "trials": sel.trials,
                "candidates": sel.candidates,
            },
        )

    def emit_outcome_span(self, turn_span_id: str, *, success: bool) -> None:
        if self._spans is None or self._last_selection is None:
            return
        self._spans.add_span_event(
            turn_span_id,
            "online_selection.outcome",
            {
                "arm_id": self._last_selection.arm.id,
                "success": success,
            },
        )
