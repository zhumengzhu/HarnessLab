"""Tests for named shell allowlist profiles."""

from __future__ import annotations

from pathlib import Path

import pytest

from harnesslab.core.models import ToolCall
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.policy.shell_profiles import (
    DEFAULT_SHELL_PROFILE,
    PROFILE_DEV,
    PROFILE_READ_ONLY,
    PROFILE_STRICT,
    resolve_shell_profile,
)


def test_default_profile_matches_dev_allowlist() -> None:
    assert resolve_shell_profile(None) == PROFILE_DEV
    assert resolve_shell_profile(DEFAULT_SHELL_PROFILE) == PROFILE_DEV


def test_strict_profile_is_subset_of_read_only() -> None:
    assert PROFILE_STRICT <= PROFILE_READ_ONLY
    assert PROFILE_READ_ONLY <= PROFILE_DEV


def test_dev_profile_allows_pytest(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path, shell_profile="dev")
    allowed, _ = policy.allow_tool(
        ToolCall(name="run_shell_safe", args={"command": "pytest -q"})
    )
    assert allowed is True


def test_strict_profile_denies_pytest(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path, shell_profile="strict")
    allowed, reason = policy.allow_tool(
        ToolCall(name="run_shell_safe", args={"command": "pytest -q"})
    )
    assert allowed is False
    assert "not in allowlist" in reason


def test_read_only_allows_ls_denies_pytest(tmp_path: Path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path, shell_profile="read_only")
    assert policy.allow_tool(ToolCall(name="run_shell_safe", args={"command": "ls"}))[0]
    assert not policy.allow_tool(
        ToolCall(name="run_shell_safe", args={"command": "pytest -q"})
    )[0]


def test_unknown_profile_raises() -> None:
    with pytest.raises(ValueError, match="unknown shell profile"):
        resolve_shell_profile("nope")
