"""Tests for operator config loading and precedence helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.operator_config import (
    OperatorConfig,
    load_operator_config,
    resolve_model_backend,
    resolve_runtime_limits,
    resolve_shell_profile,
)


def test_load_operator_config_missing_returns_defaults() -> None:
    assert load_operator_config(Path("/nonexistent/config.json")) == OperatorConfig()


def test_load_operator_config_parses_example(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[1] / "scripts" / "harnesslab.config.example.json"
    path = tmp_path / "config.json"
    path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    config = load_operator_config(path)
    assert config.model_backend == "deepseek"
    assert config.serve_port == 8787
    assert config.shell_profile == "dev"
    assert config.limits.compaction_threshold_tokens == 12000


def test_cli_flag_wins_over_config() -> None:
    config = OperatorConfig(model_backend="deepseek", shell_profile="strict")
    assert resolve_model_backend("simple", config=config) == "simple"
    assert resolve_shell_profile("read_only", config=config) == "read_only"


def test_config_wins_over_builtin_default() -> None:
    config = OperatorConfig(model_backend="deepseek", shell_profile="read_only")
    assert resolve_model_backend(None, config=config, fallback="simple") == "deepseek"
    assert resolve_shell_profile(None, config=config) == "read_only"


def test_invalid_config_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported config version"):
        load_operator_config(path)


def test_resolve_runtime_limits_prefers_explicit() -> None:
    explicit = RuntimeLimits(output_bytes_cap=123)
    config = OperatorConfig(limits=RuntimeLimits(output_bytes_cap=999))
    assert resolve_runtime_limits(explicit, config=config).output_bytes_cap == 123
