"""Local persistence for online selection arm statistics."""

from __future__ import annotations

import json
from pathlib import Path

from harnesslab.tune.online.models import ArmStats

DEFAULT_STORE_PATH = Path.home() / ".config" / "harnesslab" / "online_selection.json"


class OnlineSelectionStore:
    """JSON-backed success/trial counters keyed by arm id."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_STORE_PATH

    @property
    def path(self) -> Path:
        return self._path

    def load_stats(self) -> dict[str, ArmStats]:
        if not self._path.is_file():
            return {}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        raw = data.get("arms", {})
        if not isinstance(raw, dict):
            return {}
        out: dict[str, ArmStats] = {}
        for arm_id, payload in raw.items():
            if isinstance(payload, dict):
                out[str(arm_id)] = ArmStats.model_validate(payload)
        return out

    def get(self, arm_id: str) -> ArmStats:
        return self.load_stats().get(arm_id, ArmStats())

    def record(self, arm_id: str, *, success: bool) -> ArmStats:
        stats = self.load_stats()
        current = stats.get(arm_id, ArmStats())
        trials = current.trials + 1
        successes = current.successes + (1 if success else 0)
        updated = ArmStats(successes=successes, trials=trials)
        stats[arm_id] = updated
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"arms": {k: v.model_dump() for k, v in stats.items()}}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        return updated

    def reset(self, arm_id: str | None = None) -> None:
        if arm_id is None:
            if self._path.is_file():
                self._path.unlink()
            return
        stats = self.load_stats()
        stats.pop(arm_id, None)
        if not stats:
            if self._path.is_file():
                self._path.unlink()
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"arms": {k: v.model_dump() for k, v in stats.items()}}, indent=2)
            + "\n",
            encoding="utf-8",
        )
