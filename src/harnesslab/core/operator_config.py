"""Load operator defaults from ``~/.config/harnesslab/config.json``.

Precedence for each knob (highest wins):

1. CLI flag
2. Process environment variable
3. ``config.json``
4. Built-in default

Secrets never live in JSON — only env var *names* (e.g. ``api_key_env``).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from harnesslab.core.config import RuntimeLimits
from harnesslab.policy.shell_profiles import DEFAULT_SHELL_PROFILE
from harnesslab.providers.model_resolve import (
    resolve_anthropic_model_name,
    resolve_deepseek_model_name,
    resolve_openai_model_name,
)

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "harnesslab" / "config.json"
CONFIG_VERSION = 1


@dataclass(frozen=True)
class OperatorConfig:
    model_backend: str = "simple"
    deepseek_base_url: str | None = None
    deepseek_model_name: str | None = None
    deepseek_thinking: str = "disabled"
    deepseek_api_key_env: str = "DEEPSEEK_API_KEY"
    anthropic_model_name: str | None = None
    anthropic_thinking: str = "disabled"
    anthropic_thinking_effort: str | None = None
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
    openai_model_name: str | None = None
    openai_reasoning_effort: str = "none"
    openai_base_url: str | None = None
    openai_api_key_env: str = "OPENAI_API_KEY"
    serve_host: str = "127.0.0.1"
    serve_port: int = 8787
    serve_max_steps: int = 20
    shell_profile: str = DEFAULT_SHELL_PROFILE
    limits: RuntimeLimits = RuntimeLimits()

    def runtime_limits(self) -> RuntimeLimits:
        return self.limits


def config_path_from_env() -> Path:
    raw = os.environ.get("HARNESSLAB_CONFIG", "").strip()
    return Path(raw) if raw else DEFAULT_CONFIG_PATH


def load_operator_config(path: Path | None = None) -> OperatorConfig:
    path = path or config_path_from_env()
    if not path.is_file():
        return OperatorConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid config JSON at {path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"config root must be an object: {path}")
    return _parse_config(data)


def apply_provider_env(config: OperatorConfig) -> None:
    """Set provider env vars from config when not already in the environment."""

    if config.deepseek_base_url and not os.environ.get("DEEPSEEK_BASE_URL"):
        os.environ["DEEPSEEK_BASE_URL"] = config.deepseek_base_url
    if config.deepseek_model_name and not os.environ.get("DEEPSEEK_MODEL"):
        os.environ["DEEPSEEK_MODEL"] = config.deepseek_model_name
    if config.anthropic_model_name and not os.environ.get("ANTHROPIC_MODEL"):
        os.environ["ANTHROPIC_MODEL"] = config.anthropic_model_name
    if config.openai_model_name and not os.environ.get("OPENAI_MODEL"):
        os.environ["OPENAI_MODEL"] = config.openai_model_name
    if config.openai_base_url and not os.environ.get("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = config.openai_base_url


def resolve_model_backend(
    cli_value: str | None,
    *,
    config: OperatorConfig | None = None,
    fallback: str = "simple",
) -> str:
    if cli_value is not None:
        return cli_value
    if config is not None and config.model_backend:
        return config.model_backend
    return fallback


def resolve_shell_profile(
    cli_value: str | None,
    *,
    config: OperatorConfig | None = None,
) -> str:
    if cli_value is not None:
        return cli_value
    if config is not None:
        return config.shell_profile
    return DEFAULT_SHELL_PROFILE


def resolve_runtime_limits(
    cli_limits: RuntimeLimits | None,
    *,
    config: OperatorConfig | None = None,
) -> RuntimeLimits:
    if cli_limits is not None:
        return cli_limits
    if config is not None:
        return config.runtime_limits()
    return RuntimeLimits()


def config_settings_snapshot(
    config: OperatorConfig,
    *,
    workspace_root: Path,
    model_backend: str,
) -> dict[str, Any]:
    """Read-only settings for Web UI / health (no secrets)."""

    from harnesslab.providers.registry import model_label

    return {
        "config_path": str(config_path_from_env()),
        "workspace": str(workspace_root.resolve()),
        "model_backend": model_backend,
        "model_label": model_label(model_backend, config=config),
        "deepseek_model": resolve_deepseek_model_name(config=config),
        "deepseek_thinking": config.deepseek_thinking,
        "anthropic_model": resolve_anthropic_model_name(config=config),
        "anthropic_thinking": config.anthropic_thinking,
        "anthropic_thinking_effort": config.anthropic_thinking_effort,
        "openai_model": resolve_openai_model_name(config=config),
        "openai_reasoning_effort": config.openai_reasoning_effort,
        "shell_profile": config.shell_profile,
        "serve": {
            "host": config.serve_host,
            "port": config.serve_port,
            "max_steps": config.serve_max_steps,
        },
        "limits": asdict(config.limits),
    }


def _parse_config(data: dict[str, Any]) -> OperatorConfig:
    version = data.get("version", CONFIG_VERSION)
    if version != CONFIG_VERSION:
        raise ValueError(f"unsupported config version {version!r} (expected {CONFIG_VERSION})")

    model = data.get("model", {})
    if not isinstance(model, dict):
        raise ValueError("model must be an object")

    deepseek = model.get("deepseek", {})
    if deepseek is not None and not isinstance(deepseek, dict):
        raise ValueError("model.deepseek must be an object")

    anthropic = model.get("anthropic", {})
    if anthropic is not None and not isinstance(anthropic, dict):
        raise ValueError("model.anthropic must be an object")

    openai = model.get("openai", {})
    if openai is not None and not isinstance(openai, dict):
        raise ValueError("model.openai must be an object")

    serve = data.get("serve", {})
    if not isinstance(serve, dict):
        raise ValueError("serve must be an object")

    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")

    limits_raw = data.get("limits", {})
    if not isinstance(limits_raw, dict):
        raise ValueError("limits must be an object")

    limits = RuntimeLimits(
        **{k: v for k, v in limits_raw.items() if k in RuntimeLimits.__dataclass_fields__}
    )

    return OperatorConfig(
        model_backend=str(model.get("default_backend", "simple")),
        deepseek_base_url=_optional_str(deepseek.get("base_url")),
        deepseek_model_name=_optional_str(deepseek.get("model_name")),
        deepseek_thinking=str(deepseek.get("thinking", "disabled")),
        deepseek_api_key_env=str(deepseek.get("api_key_env", "DEEPSEEK_API_KEY")),
        anthropic_model_name=_optional_str(anthropic.get("model_name")),
        anthropic_thinking=_anthropic_thinking_mode(anthropic),
        anthropic_thinking_effort=_optional_str(anthropic.get("effort")),
        anthropic_api_key_env=str(anthropic.get("api_key_env", "ANTHROPIC_API_KEY")),
        openai_model_name=_optional_str(openai.get("model_name")),
        openai_reasoning_effort=str(openai.get("reasoning_effort", "none")),
        openai_base_url=_optional_str(openai.get("base_url")),
        openai_api_key_env=str(openai.get("api_key_env", "OPENAI_API_KEY")),
        serve_host=str(serve.get("host", "127.0.0.1")),
        serve_port=int(serve.get("port", 8787)),
        serve_max_steps=int(serve.get("max_steps", 20)),
        shell_profile=str(policy.get("shell_profile", DEFAULT_SHELL_PROFILE)),
        limits=limits,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _anthropic_thinking_mode(anthropic: dict[str, Any]) -> str:
    thinking = anthropic.get("thinking")
    if isinstance(thinking, str):
        return thinking.strip() or "disabled"
    if isinstance(thinking, dict):
        mode = thinking.get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return "disabled"
