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


def test_load_operator_config_parses_failover_and_gemini(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "model": {
                    "default_backend": "gemini",
                    "failover_enabled": True,
                    "fallbacks": ["simple", "deepseek/deepseek-v4-pro"],
                    "gemini": {
                        "model_name": "gemini-3-flash-preview",
                        "thinking_level": "high",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_operator_config(path)
    assert config.model_backend == "gemini"
    assert config.model_failover_enabled is True
    assert config.model_fallbacks == ("simple", "deepseek")
    assert config.gemini_model_name == "gemini-3-flash-preview"
    assert config.gemini_thinking_level == "high"


def test_load_operator_config_parses_tools_block(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "tools": {
                    "fetch_url": {
                        "mode": "open",
                        "allowlist": ["wttr.in", "example.com"],
                        "deny_hosts": ["bad.example"],
                    },
                    "web_search": {
                        "backend": "tavily",
                        "max_results": 8,
                        "api_key_env": "TAVILY_API_KEY",
                        "api_base_url": "https://api.tavily.com",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_operator_config(path)
    assert config.fetch_url_mode == "open"
    assert config.fetch_url_allowlist == ("wttr.in", "example.com")
    assert config.fetch_url_deny_hosts == ("bad.example",)
    assert config.web_search_backend == "tavily"
    assert config.web_search_max_results == 8
    assert config.web_search_api_key_env == "TAVILY_API_KEY"


def test_invalid_config_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported config version"):
        load_operator_config(path)


def test_resolve_runtime_limits_prefers_explicit() -> None:
    explicit = RuntimeLimits(output_bytes_cap=123)
    config = OperatorConfig(limits=RuntimeLimits(output_bytes_cap=999))
    assert resolve_runtime_limits(explicit, config=config).output_bytes_cap == 123
