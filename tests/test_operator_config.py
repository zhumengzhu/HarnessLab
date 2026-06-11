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


def test_save_operator_config_persists_model_defaults(tmp_path: Path) -> None:
    from harnesslab.core.operator_config import save_operator_config
    from harnesslab.providers.deepseek_config import apply_deepseek_ui_effort

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "model": {"default_backend": "simple"},
                "policy": {"shell_profile": "dev"},
            }
        ),
        encoding="utf-8",
    )
    thinking, reasoning = apply_deepseek_ui_effort("max")
    config = OperatorConfig(
        model_backend="deepseek",
        deepseek_model_name="deepseek-v4-pro",
        deepseek_thinking=thinking,
        deepseek_reasoning_effort=reasoning,
    )
    save_operator_config(config, path=path)

    reloaded = load_operator_config(path)
    assert reloaded.model_backend == "deepseek"
    assert reloaded.deepseek_model_name == "deepseek-v4-pro"
    assert reloaded.deepseek_thinking == "enabled"
    assert reloaded.deepseek_reasoning_effort == "max"

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["policy"]["shell_profile"] == "dev"


def test_cli_flag_wins_over_config() -> None:
    config = OperatorConfig(model_backend="deepseek", shell_profile="strict")
    assert resolve_model_backend("simple", config=config) == "simple"
    assert resolve_shell_profile("read_only", config=config) == "read_only"


def test_config_wins_over_builtin_default() -> None:
    config = OperatorConfig(model_backend="deepseek", shell_profile="read_only")
    assert resolve_model_backend(None, config=config, fallback="simple") == "deepseek"
    assert resolve_shell_profile(None, config=config) == "read_only"


def test_load_operator_config_parses_deepseek_reasoning_effort(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "model": {
                    "default_backend": "deepseek",
                    "deepseek": {
                        "model_name": "deepseek-v4-pro",
                        "thinking": "max",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_operator_config(path)
    assert config.deepseek_model_name == "deepseek-v4-pro"
    assert config.deepseek_thinking == "enabled"
    assert config.deepseek_reasoning_effort == "max"


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


def test_patch_model_failover_writes_config(tmp_path: Path) -> None:
    from harnesslab.core.operator_config import load_operator_config, patch_model_failover

    path = tmp_path / "config.json"
    path.write_text('{"version": 1, "model": {"default_backend": "deepseek"}}\n')
    patch_model_failover(enabled=True, fallbacks=["simple", "anthropic"], path=path)
    config = load_operator_config(path)
    assert config.model_failover_enabled is True
    assert config.model_fallbacks == ("simple", "anthropic")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["model"]["failover_enabled"] is True
    assert saved["model"]["fallbacks"] == ["simple", "anthropic"]


def test_load_operator_config_parses_web_search_fallback(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "tools": {
                    "web_search": {
                        "backend": "ddgs",
                        "fallback_backend": "tavily",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_operator_config(path)
    assert config.web_search_backend == "ddgs"
    assert config.web_search_fallback_backend == "tavily"


def test_load_operator_config_parses_tools_block(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "loop": {
                    "planning_mode": "required",
                    "replan_after_steps": 3,
                    "budget": {
                        "enabled": True,
                        "soft_ratio": 0.75,
                        "action_on_hard": "ask_user",
                        "max_llm_calls_per_turn": 8,
                        "max_tool_calls_per_turn": 12,
                        "max_turn_wall_time_ms": 30000,
                        "max_session_tokens_total": 200000,
                        "max_session_tool_calls_total": 100,
                        "max_session_wall_time_ms_total": 600000,
                        "max_session_cost_usd_total": 5.0,
                    },
                },
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
                    "skills": {
                        "selection_mode": "model",
                    },
                    "hooks": {
                        "pre_tool": [
                            {
                                "name": "pre-block-shell",
                                "type": "prompt",
                                "config": {
                                    "tool_name_contains": "run_shell_safe",
                                    "action": "block",
                                    "reason": "blocked by test",
                                },
                            }
                        ],
                        "post_tool": [
                            {
                                "name": "post-audit",
                                "type": "http",
                                "config": {"url": "https://example.com/hook"},
                            }
                        ],
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
    assert config.skill_selection_mode == "model"
    assert config.planning_mode == "required"
    assert config.replan_after_steps == 3
    assert config.budget_enabled is True
    assert config.budget_soft_ratio == 0.75
    assert config.budget_action_on_hard == "ask_user"
    assert config.budget_max_llm_calls_per_turn == 8
    assert config.budget_max_tool_calls_per_turn == 12
    assert config.budget_max_turn_wall_time_ms == 30000
    assert config.budget_max_session_tokens_total == 200000
    assert config.budget_max_session_tool_calls_total == 100
    assert config.budget_max_session_wall_time_ms_total == 600000
    assert config.budget_max_session_cost_usd_total == 5.0
    assert len(config.pre_tool_hooks) == 1
    assert config.pre_tool_hooks[0]["name"] == "pre-block-shell"
    assert config.pre_tool_hooks[0]["type"] == "prompt"
    assert len(config.post_tool_hooks) == 1
    assert config.post_tool_hooks[0]["type"] == "http"


def test_load_operator_config_parses_json5_comments(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        """{
  // pick the local deterministic backend for eval
  "version": 1,
  "model": {
    "default_backend": "simple",
  },
}""",
        encoding="utf-8",
    )
    config = load_operator_config(path)
    assert config.model_backend == "simple"


def test_read_config_source_text_returns_file_body(tmp_path: Path) -> None:
    from harnesslab.core.operator_config import read_config_source_text

    path = tmp_path / "config.json"
    text = '{ "version": 1, "model": { "default_backend": "simple" } }'
    path.write_text(text, encoding="utf-8")
    assert read_config_source_text(path) == text


def test_invalid_config_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported config version"):
        load_operator_config(path)


def test_resolve_runtime_limits_prefers_explicit() -> None:
    explicit = RuntimeLimits(output_bytes_cap=123)
    config = OperatorConfig(limits=RuntimeLimits(output_bytes_cap=999))
    assert resolve_runtime_limits(explicit, config=config).output_bytes_cap == 123
