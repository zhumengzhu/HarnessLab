"""Tests for the tuning search space (Layer B1)."""

from __future__ import annotations

import pytest

from harnesslab.tune.space import (
    DEFAULT_CONFIG,
    DEFAULT_SEARCH_SPACE,
    CategoricalDim,
    IntDim,
    SearchSpace,
)


def _small_space() -> SearchSpace:
    return SearchSpace(
        [
            CategoricalDim("shell_profile", ("dev", "strict")),
            IntDim("output_bytes_cap", (1, 2, 4)),
        ]
    )


def test_grid_is_full_cartesian_product_and_deterministic() -> None:
    space = _small_space()
    grid1 = space.grid()
    grid2 = space.grid()
    assert len(grid1) == space.size == 6
    assert grid1 == grid2  # stable order


def test_encode_normalizes_by_index_position() -> None:
    space = _small_space()
    assert space.encode({"shell_profile": "dev", "output_bytes_cap": 1}) == (0.0, 0.0)
    assert space.encode({"shell_profile": "strict", "output_bytes_cap": 4}) == (1.0, 1.0)
    assert space.encode({"shell_profile": "dev", "output_bytes_cap": 2}) == (0.0, 0.5)


def test_encode_rejects_unknown_value() -> None:
    space = _small_space()
    with pytest.raises(ValueError):
        space.encode({"shell_profile": "dev", "output_bytes_cap": 999})


def test_duplicate_dimension_names_rejected() -> None:
    with pytest.raises(ValueError):
        SearchSpace([IntDim("x", (1, 2)), IntDim("x", (3, 4))])


def test_empty_space_rejected() -> None:
    with pytest.raises(ValueError):
        SearchSpace([])


def test_default_config_is_a_grid_point() -> None:
    grid = DEFAULT_SEARCH_SPACE.grid()
    clamped = DEFAULT_SEARCH_SPACE.clamp(DEFAULT_CONFIG)
    assert clamped in grid


def test_clamp_keeps_only_known_dims() -> None:
    space = _small_space()
    clamped = space.clamp(
        {"shell_profile": "dev", "output_bytes_cap": 1, "extraneous": 7}
    )
    assert clamped == {"shell_profile": "dev", "output_bytes_cap": 1}
