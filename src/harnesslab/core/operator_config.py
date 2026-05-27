"""Load operator defaults from ``~/.config/harnesslab/config.json``.

The file may be strict JSON or **JSON5** (``//`` / ``/* */`` comments,
trailing commas, unquoted keys). Parsing uses the ``json5`` package.

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
from typing import Any, Literal

import json5

from harnesslab.core.config import RuntimeLimits
from harnesslab.policy.shell_profiles import DEFAULT_SHELL_PROFILE
from harnesslab.providers.model_resolve import (
    resolve_anthropic_model_name,
    resolve_deepseek_model_name,
    resolve_gemini_model_name,
    resolve_openai_model_name,
)
from harnesslab.tools.research_tools import (
    DEFAULT_WEB_SEARCH_BACKEND,
    DEFAULT_WEB_SEARCH_MAX_RESULTS,
)

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "harnesslab" / "config.json"
CONFIG_VERSION = 1


@dataclass(frozen=True)
class OperatorConfig:
    model_backend: str = "simple"
    deepseek_base_url: str | None = None
    deepseek_model_name: str | None = None
    deepseek_thinking: str = "disabled"
    deepseek_reasoning_effort: str | None = None
    deepseek_api_key_env: str = "DEEPSEEK_API_KEY"
    anthropic_model_name: str | None = None
    anthropic_thinking: str = "disabled"
    anthropic_thinking_effort: str | None = None
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
    openai_model_name: str | None = None
    openai_reasoning_effort: str = "none"
    openai_base_url: str | None = None
    openai_api_key_env: str = "OPENAI_API_KEY"
    gemini_model_name: str | None = None
    gemini_thinking_budget: int | None = None
    gemini_thinking_level: str | None = None
    gemini_api_key_env: str = "GOOGLE_API_KEY"
    model_failover_enabled: bool = False
    model_fallbacks: tuple[str, ...] = ()
    fetch_url_mode: Literal["auto", "strict", "open"] = "auto"
    fetch_url_allowlist: tuple[str, ...] = ("wttr.in",)
    fetch_url_deny_hosts: tuple[str, ...] = ()
    web_search_backend: str = DEFAULT_WEB_SEARCH_BACKEND
    web_search_max_results: int = DEFAULT_WEB_SEARCH_MAX_RESULTS
    web_search_api_key_env: str | None = None
    web_search_api_base_url: str | None = None
    skill_selection_mode: Literal["heuristic", "model"] = "heuristic"
    planning_mode: Literal["off", "hint", "required"] = "off"
    replan_after_steps: int | None = None
    budget_enabled: bool = False
    budget_soft_ratio: float = 0.8
    budget_action_on_hard: Literal["ask_user", "final", "error"] = "ask_user"
    budget_max_llm_calls_per_turn: int | None = None
    budget_max_tool_calls_per_turn: int | None = None
    budget_max_turn_wall_time_ms: int | None = None
    budget_max_session_tokens_total: int | None = None
    budget_max_session_tool_calls_total: int | None = None
    budget_max_session_wall_time_ms_total: int | None = None
    budget_max_session_cost_usd_total: float | None = None
    mcp_servers: tuple[dict[str, Any], ...] = ()
    mcp_allowed_tools: tuple[str, ...] = ()
    python_sandbox_profile: Literal["disabled", "local", "strict"] = "disabled"
    multi_agent_enabled: bool = False
    web_ui_version: Literal["legacy", "ts"] = "ts"
    pre_tool_hooks: tuple[dict[str, Any], ...] = ()
    post_tool_hooks: tuple[dict[str, Any], ...] = ()
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


def read_config_source_text(path: Path | None = None) -> str | None:
    """Return raw on-disk config text for Web UI display (may include JSON5 comments)."""

    path = path or config_path_from_env()
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def load_operator_config(path: Path | None = None) -> OperatorConfig:
    path = path or config_path_from_env()
    if not path.is_file():
        return OperatorConfig()
    try:
        data = json5.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"invalid config JSON5 at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"config root must be an object: {path}")
    return _parse_config(data)


def save_operator_config(config: OperatorConfig, path: Path | None = None) -> Path:
    """Persist operator model defaults to ``config.json`` (merge into existing file)."""

    path = path or config_path_from_env()
    if path.is_file():
        raw = path.read_text(encoding="utf-8")
        data = json5.loads(raw)
        if not isinstance(data, dict):
            data = {"version": CONFIG_VERSION}
    else:
        data = {"version": CONFIG_VERSION}

    _patch_model_section(data, config)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def patch_loop_multi_agent_enabled(*, enabled: bool, path: Path | None = None) -> Path:
    """Merge ``loop.multi_agent.enabled`` into the on-disk config file."""

    path = path or config_path_from_env()
    if path.is_file():
        data = json5.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {"version": CONFIG_VERSION}
    else:
        data = {"version": CONFIG_VERSION}

    loop_raw = data.get("loop")
    loop: dict[str, Any] = loop_raw if isinstance(loop_raw, dict) else {}
    data["loop"] = loop
    multi_raw = loop.get("multi_agent")
    multi: dict[str, Any] = multi_raw if isinstance(multi_raw, dict) else {}
    loop["multi_agent"] = multi
    multi["enabled"] = bool(enabled)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def _patch_model_section(data: dict[str, Any], config: OperatorConfig) -> None:
    from harnesslab.providers.deepseek_config import deepseek_ui_effort

    data["version"] = CONFIG_VERSION
    model_raw = data.get("model")
    model: dict[str, Any] = model_raw if isinstance(model_raw, dict) else {}
    data["model"] = model

    model["default_backend"] = config.model_backend

    deepseek = model.get("deepseek")
    ds: dict[str, Any] = deepseek if isinstance(deepseek, dict) else {}
    model["deepseek"] = ds
    if config.deepseek_model_name:
        ds["model_name"] = config.deepseek_model_name
    if config.deepseek_base_url:
        ds["base_url"] = config.deepseek_base_url
    ds["api_key_env"] = config.deepseek_api_key_env
    ui_effort = deepseek_ui_effort(
        thinking_mode=config.deepseek_thinking,
        reasoning_effort=config.deepseek_reasoning_effort,
    )
    ds["thinking"] = ui_effort
    if ui_effort == "high":
        ds["reasoning_effort"] = "high"
    else:
        ds.pop("reasoning_effort", None)

    anthropic = model.get("anthropic")
    ant: dict[str, Any] = anthropic if isinstance(anthropic, dict) else {}
    model["anthropic"] = ant
    if config.anthropic_model_name:
        ant["model_name"] = config.anthropic_model_name
    ant["api_key_env"] = config.anthropic_api_key_env
    if config.anthropic_thinking == "enabled" and config.anthropic_thinking_effort:
        ant["thinking"] = {
            "mode": "adaptive",
            "effort": config.anthropic_thinking_effort,
        }
    elif config.anthropic_thinking not in {"", "disabled"}:
        ant["thinking"] = config.anthropic_thinking
    else:
        ant["thinking"] = "disabled"

    openai = model.get("openai")
    oai: dict[str, Any] = openai if isinstance(openai, dict) else {}
    model["openai"] = oai
    if config.openai_model_name:
        oai["model_name"] = config.openai_model_name
    if config.openai_base_url:
        oai["base_url"] = config.openai_base_url
    oai["api_key_env"] = config.openai_api_key_env
    oai["reasoning_effort"] = config.openai_reasoning_effort

    gemini = model.get("gemini")
    gem: dict[str, Any] = gemini if isinstance(gemini, dict) else {}
    model["gemini"] = gem
    if config.gemini_model_name:
        gem["model_name"] = config.gemini_model_name
    gem["api_key_env"] = config.gemini_api_key_env
    if config.gemini_thinking_budget is not None:
        gem["thinking_budget"] = config.gemini_thinking_budget
    if config.gemini_thinking_level:
        gem["thinking_level"] = config.gemini_thinking_level
    elif "thinking_level" in gem and config.gemini_thinking_level is None:
        gem.pop("thinking_level", None)


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
    if config.gemini_model_name and not os.environ.get("GEMINI_MODEL"):
        os.environ["GEMINI_MODEL"] = config.gemini_model_name


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
        "deepseek_reasoning_effort": config.deepseek_reasoning_effort,
        "anthropic_model": resolve_anthropic_model_name(config=config),
        "anthropic_thinking": config.anthropic_thinking,
        "anthropic_thinking_effort": config.anthropic_thinking_effort,
        "openai_model": resolve_openai_model_name(config=config),
        "openai_reasoning_effort": config.openai_reasoning_effort,
        "gemini_model": resolve_gemini_model_name(config=config),
        "gemini_thinking_budget": config.gemini_thinking_budget,
        "gemini_thinking_level": config.gemini_thinking_level,
        "model_failover_enabled": config.model_failover_enabled,
        "model_fallbacks": list(config.model_fallbacks),
        "fetch_url_mode": config.fetch_url_mode,
        "fetch_url_allowlist": list(config.fetch_url_allowlist),
        "fetch_url_deny_hosts": list(config.fetch_url_deny_hosts),
        "web_search_backend": config.web_search_backend,
        "web_search_max_results": config.web_search_max_results,
        "web_search_api_base_url": config.web_search_api_base_url,
        "skill_selection_mode": config.skill_selection_mode,
        "planning_mode": config.planning_mode,
        "replan_after_steps": config.replan_after_steps,
        "budget": {
            "enabled": config.budget_enabled,
            "soft_ratio": config.budget_soft_ratio,
            "action_on_hard": config.budget_action_on_hard,
            "max_llm_calls_per_turn": config.budget_max_llm_calls_per_turn,
            "max_tool_calls_per_turn": config.budget_max_tool_calls_per_turn,
            "max_turn_wall_time_ms": config.budget_max_turn_wall_time_ms,
            "max_session_tokens_total": config.budget_max_session_tokens_total,
            "max_session_tool_calls_total": config.budget_max_session_tool_calls_total,
            "max_session_wall_time_ms_total": config.budget_max_session_wall_time_ms_total,
            "max_session_cost_usd_total": config.budget_max_session_cost_usd_total,
        },
        "mcp_servers": list(config.mcp_servers),
        "mcp_allowed_tools": list(config.mcp_allowed_tools),
        "python_sandbox_profile": config.python_sandbox_profile,
        "multi_agent_enabled": config.multi_agent_enabled,
        "web_ui_version": config.web_ui_version,
        "hooks": {
            "pre_tool": list(config.pre_tool_hooks),
            "post_tool": list(config.post_tool_hooks),
        },
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

    gemini = model.get("gemini", {})
    if gemini is not None and not isinstance(gemini, dict):
        raise ValueError("model.gemini must be an object")

    serve = data.get("serve", {})
    if not isinstance(serve, dict):
        raise ValueError("serve must be an object")

    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")

    tools = data.get("tools", {})
    if not isinstance(tools, dict):
        raise ValueError("tools must be an object")

    fetch_url = tools.get("fetch_url", {})
    if fetch_url is not None and not isinstance(fetch_url, dict):
        raise ValueError("tools.fetch_url must be an object")

    web_search = tools.get("web_search", {})
    if web_search is not None and not isinstance(web_search, dict):
        raise ValueError("tools.web_search must be an object")
    skills = tools.get("skills", {})
    if skills is not None and not isinstance(skills, dict):
        raise ValueError("tools.skills must be an object")
    hooks = tools.get("hooks", {})
    if hooks is not None and not isinstance(hooks, dict):
        raise ValueError("tools.hooks must be an object")
    loop = data.get("loop", {})
    if not isinstance(loop, dict):
        raise ValueError("loop must be an object")
    budget = loop.get("budget", {})
    if budget is not None and not isinstance(budget, dict):
        raise ValueError("loop.budget must be an object")

    limits_raw = data.get("limits", {})
    if not isinstance(limits_raw, dict):
        raise ValueError("limits must be an object")

    limits = RuntimeLimits(
        **{k: v for k, v in limits_raw.items() if k in RuntimeLimits.__dataclass_fields__}
    )

    from harnesslab.providers.deepseek_config import parse_deepseek_thinking_fields

    ds_thinking, ds_effort = parse_deepseek_thinking_fields(
        thinking_raw=deepseek.get("thinking", "disabled"),
        reasoning_effort_raw=deepseek.get("reasoning_effort"),
    )

    return OperatorConfig(
        model_backend=str(model.get("default_backend", "simple")),
        deepseek_base_url=_optional_str(deepseek.get("base_url")),
        deepseek_model_name=_optional_str(deepseek.get("model_name")),
        deepseek_thinking=ds_thinking,
        deepseek_reasoning_effort=ds_effort,
        deepseek_api_key_env=str(deepseek.get("api_key_env", "DEEPSEEK_API_KEY")),
        anthropic_model_name=_optional_str(anthropic.get("model_name")),
        anthropic_thinking=_anthropic_thinking_mode(anthropic),
        anthropic_thinking_effort=_optional_str(anthropic.get("effort")),
        anthropic_api_key_env=str(anthropic.get("api_key_env", "ANTHROPIC_API_KEY")),
        openai_model_name=_optional_str(openai.get("model_name")),
        openai_reasoning_effort=str(openai.get("reasoning_effort", "none")),
        openai_base_url=_optional_str(openai.get("base_url")),
        openai_api_key_env=str(openai.get("api_key_env", "OPENAI_API_KEY")),
        gemini_model_name=_optional_str(gemini.get("model_name")),
        gemini_thinking_budget=_optional_int(gemini.get("thinking_budget")),
        gemini_thinking_level=_optional_str(gemini.get("thinking_level")),
        gemini_api_key_env=str(gemini.get("api_key_env", "GOOGLE_API_KEY")),
        model_failover_enabled=bool(model.get("failover_enabled", False)),
        model_fallbacks=_parse_fallbacks(model.get("fallbacks")),
        fetch_url_mode=_fetch_mode(fetch_url),
        fetch_url_allowlist=_parse_hosts(fetch_url.get("allowlist"), default=("wttr.in",)),
        fetch_url_deny_hosts=_parse_hosts(fetch_url.get("deny_hosts"), default=()),
        web_search_backend=_optional_str(web_search.get("backend")) or DEFAULT_WEB_SEARCH_BACKEND,
        web_search_max_results=_optional_int(web_search.get("max_results"))
        or DEFAULT_WEB_SEARCH_MAX_RESULTS,
        web_search_api_key_env=_optional_str(web_search.get("api_key_env")),
        web_search_api_base_url=_optional_str(web_search.get("api_base_url")),
        skill_selection_mode=_skill_selection_mode(skills),
        planning_mode=_planning_mode(loop),
        replan_after_steps=_optional_int(loop.get("replan_after_steps")),
        budget_enabled=bool(budget.get("enabled", False)),
        budget_soft_ratio=_budget_soft_ratio(budget),
        budget_action_on_hard=_budget_action_on_hard(budget),
        budget_max_llm_calls_per_turn=_optional_int(
            budget.get("max_llm_calls_per_turn")
        ),
        budget_max_tool_calls_per_turn=_optional_int(
            budget.get("max_tool_calls_per_turn")
        ),
        budget_max_turn_wall_time_ms=_optional_int(budget.get("max_turn_wall_time_ms")),
        budget_max_session_tokens_total=_optional_int(
            budget.get("max_session_tokens_total")
        ),
        budget_max_session_tool_calls_total=_optional_int(
            budget.get("max_session_tool_calls_total")
        ),
        budget_max_session_wall_time_ms_total=_optional_int(
            budget.get("max_session_wall_time_ms_total")
        ),
        budget_max_session_cost_usd_total=_optional_float(
            budget.get("max_session_cost_usd_total")
        ),
        mcp_servers=_parse_mcp_servers(tools.get("mcp_servers")),
        mcp_allowed_tools=_parse_str_list(tools.get("mcp_allowed_tools")),
        python_sandbox_profile=_python_sandbox_profile(policy),
        multi_agent_enabled=bool(loop.get("multi_agent", {}).get("enabled", False)),
        web_ui_version=_web_ui_version(data.get("web", {})),
        pre_tool_hooks=_parse_hook_list(hooks.get("pre_tool")),
        post_tool_hooks=_parse_hook_list(hooks.get("post_tool")),
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


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text)


def _parse_fallbacks(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        backend = item.strip().lower()
        if not backend:
            continue
        if "/" in backend:
            backend = backend.split("/", 1)[0].strip()
        if backend and backend not in out:
            out.append(backend)
    return tuple(out)


def _parse_hosts(value: Any, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = [str(v) for v in value]
    else:
        return default
    out: list[str] = []
    for item in items:
        host = item.strip().lower()
        if host and host not in out:
            out.append(host)
    return tuple(out) if out else default


def _fetch_mode(fetch_url: dict[str, Any]) -> Literal["auto", "strict", "open"]:
    mode = str(fetch_url.get("mode", "auto")).strip().lower()
    if mode not in {"auto", "strict", "open"}:
        return "auto"
    return mode  # type: ignore[return-value]


def _anthropic_thinking_mode(anthropic: dict[str, Any]) -> str:
    thinking = anthropic.get("thinking")
    if isinstance(thinking, str):
        return thinking.strip() or "disabled"
    if isinstance(thinking, dict):
        mode = thinking.get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return "disabled"


def _skill_selection_mode(skills: dict[str, Any]) -> Literal["heuristic", "model"]:
    mode = str(skills.get("selection_mode", "heuristic")).strip().lower()
    if mode not in {"heuristic", "model"}:
        return "heuristic"
    return mode  # type: ignore[return-value]


def _planning_mode(loop: dict[str, Any]) -> Literal["off", "hint", "required"]:
    mode = str(loop.get("planning_mode", "off")).strip().lower()
    if mode not in {"off", "hint", "required"}:
        return "off"
    return mode  # type: ignore[return-value]


def _budget_soft_ratio(budget: dict[str, Any]) -> float:
    raw = budget.get("soft_ratio", 0.8)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.8
    if value <= 0:
        return 0.8
    if value >= 1:
        return 1.0
    return value


def _budget_action_on_hard(
    budget: dict[str, Any],
) -> Literal["ask_user", "final", "error"]:
    mode = str(budget.get("action_on_hard", "ask_user")).strip().lower()
    if mode not in {"ask_user", "final", "error"}:
        return "ask_user"
    return mode  # type: ignore[return-value]


def _parse_hook_list(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _optional_str(item.get("name")) or "hook"
        hook_type = (_optional_str(item.get("type")) or "prompt").lower()
        if hook_type not in {"prompt", "shell", "http"}:
            hook_type = "prompt"
        config = item.get("config", {})
        if not isinstance(config, dict):
            config = {}
        out.append({"name": name, "type": hook_type, "config": config})
    return tuple(out)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_str_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _parse_mcp_servers(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _optional_str(item.get("name"))
        command = _optional_str(item.get("command"))
        if not name or not command:
            continue
        args_raw = item.get("args", [])
        args = tuple(str(a) for a in args_raw) if isinstance(args_raw, list) else ()
        env_names = _parse_str_list(item.get("env_names"))
        out.append(
            {
                "name": name,
                "command": command,
                "args": args,
                "env_names": env_names,
                "policy_profile": str(item.get("policy_profile", "strict")),
            }
        )
    return tuple(out)


def _python_sandbox_profile(policy: dict[str, Any]) -> Literal["disabled", "local", "strict"]:
    mode = str(policy.get("python_sandbox", "disabled")).strip().lower()
    if mode not in {"disabled", "local", "strict"}:
        return "disabled"
    return mode  # type: ignore[return-value]


def _web_ui_version(web: Any) -> Literal["legacy", "ts"]:
    if not isinstance(web, dict):
        return "ts"
    mode = str(web.get("ui_version", "ts")).strip().lower()
    if mode not in {"legacy", "ts"}:
        return "ts"
    return mode  # type: ignore[return-value]
