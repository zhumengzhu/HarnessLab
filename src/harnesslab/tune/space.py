"""Declarative search space over runtime configuration knobs.

A ``SearchSpace`` is an ordered list of dimensions; each dimension is a small,
explicit set of candidate values (integers or categoricals). The space can
enumerate its full grid (cartesian product) and encode any config into a
normalized ``[0, 1]^d`` vector for the Gaussian-process surrogate. Encoding is
index-based (position within the dimension's value list), which keeps the
geometry well-defined for both numeric and categorical knobs.

Only knobs the deterministic eval models actually react to belong here:
``RuntimeLimits`` fields plus ``shell_profile``. See the module docstring of
``harnesslab.tune`` for why prompt/sampling knobs are excluded.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

ConfigValue = int | str
Config = dict[str, ConfigValue]


@dataclass(frozen=True)
class IntDim:
    name: str
    levels: tuple[int, ...]

    def values(self) -> tuple[ConfigValue, ...]:
        return self.levels


@dataclass(frozen=True)
class CategoricalDim:
    name: str
    choices: tuple[str, ...]

    def values(self) -> tuple[ConfigValue, ...]:
        return self.choices


Dimension = IntDim | CategoricalDim


class SearchSpace:
    """An ordered set of named dimensions with finite candidate values."""

    def __init__(self, dims: list[Dimension]) -> None:
        if not dims:
            raise ValueError("SearchSpace requires at least one dimension")
        names = [d.name for d in dims]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate dimension names: {names}")
        self._dims = list(dims)

    @property
    def dims(self) -> list[Dimension]:
        return list(self._dims)

    @property
    def names(self) -> list[str]:
        return [d.name for d in self._dims]

    def grid(self) -> list[Config]:
        """All configs in the cartesian product, in a deterministic order."""

        value_lists = [d.values() for d in self._dims]
        configs: list[Config] = []
        for combo in itertools.product(*value_lists):
            configs.append(
                {d.name: value for d, value in zip(self._dims, combo, strict=True)}
            )
        return configs

    @property
    def size(self) -> int:
        total = 1
        for d in self._dims:
            total *= len(d.values())
        return total

    def encode(self, config: Config) -> tuple[float, ...]:
        """Normalize a config to ``[0, 1]^d`` by each value's index position."""

        vector: list[float] = []
        for d in self._dims:
            values = d.values()
            if config[d.name] not in values:
                raise ValueError(
                    f"value {config[d.name]!r} not a level of dimension {d.name!r}"
                )
            idx = values.index(config[d.name])
            denom = len(values) - 1
            vector.append(idx / denom if denom > 0 else 0.0)
        return tuple(vector)

    def clamp(self, config: Config) -> Config:
        """Return ``config`` restricted to this space's known dimensions."""

        return {d.name: config[d.name] for d in self._dims if d.name in config}


def _to_runtime_limits_keys(config: Config) -> dict[str, Any]:
    """Split a config into ``RuntimeLimits`` field overrides (drops shell_profile)."""

    return {k: v for k, v in config.items() if k != "shell_profile"}


# Default tunable space: knobs the deterministic eval reacts to. Each numeric
# dimension includes the current ``RuntimeLimits`` default as a level so the
# baseline configuration is always reachable (and evaluated first).
DEFAULT_SEARCH_SPACE = SearchSpace(
    [
        CategoricalDim("shell_profile", ("dev", "read_only", "strict")),
        IntDim("context_window_tokens", (8000, 16000, 32000)),
        IntDim("compaction_threshold_tokens", (4000, 8000, 12000, 16000)),
        IntDim("compaction_keep_last_messages", (2, 4, 6, 8)),
        IntDim("output_bytes_cap", (16384, 32768, 65536, 131072)),
    ]
)

DEFAULT_CONFIG: Config = {
    "shell_profile": "dev",
    "context_window_tokens": 16000,
    "compaction_threshold_tokens": 12000,
    "compaction_keep_last_messages": 4,
    "output_bytes_cap": 65536,
}
