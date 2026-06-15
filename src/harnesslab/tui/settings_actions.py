"""TUI operator actions: hot-reload model and failover from slash commands."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.operator_config import (
    OperatorConfig,
    load_operator_config,
    patch_model_failover,
    save_operator_config,
)
from harnesslab.providers.context_limits import (
    align_runtime_limits_with_model,
    model_id_for_backend,
)
from harnesslab.providers.registry import create_model, normalize_backend

_TUI_BACKENDS = frozenset({"simple", "deepseek", "anthropic", "openai", "gemini"})


def install_loop_model(
    loop: HarnessLoop,
    *,
    workspace_root: Path,
    backend: str,
    config: OperatorConfig | None,
    model_id: str | None = None,
) -> str:
    """Replace ``loop._model`` and align limits; return normalized backend id."""

    from harnesslab.cli import _make_dynamic_blocks_provider  # noqa: PLC0415
    from harnesslab.providers.deepseek import tool_specs_from_registry  # noqa: PLC0415

    norm = normalize_backend(backend, fallback=config.model_backend if config else "simple")
    model = create_model(
        norm,
        config=config,
        tool_specs_provider=lambda: tool_specs_from_registry(loop._tools.list()),  # noqa: SLF001
        dynamic_blocks_provider=_make_dynamic_blocks_provider(
            workspace_root,
            loop._tools,  # noqa: SLF001
            skill_selection_mode="heuristic",
            planning_mode="off",
        ),
    )
    loop._model = model  # noqa: SLF001
    resolved_model_id = model_id or model_id_for_backend(norm, config=config)
    loop._limits = align_runtime_limits_with_model(  # noqa: SLF001
        loop._limits,
        backend=norm,
        config=config,
        model_id=resolved_model_id,
    )
    return norm


def apply_model_backend(
    loop: HarnessLoop,
    *,
    workspace_root: Path,
    config: OperatorConfig,
    backend: str,
) -> tuple[OperatorConfig, str]:
    norm = normalize_backend(backend.strip().lower(), fallback=config.model_backend)
    if norm not in _TUI_BACKENDS:
        raise ValueError(f"unsupported backend {backend!r}; choose from {_TUI_BACKENDS}")
    updated = replace(config, model_backend=norm)
    save_operator_config(updated)
    install_loop_model(loop, workspace_root=workspace_root, backend=norm, config=updated)
    return updated, norm


def apply_failover(
    loop: HarnessLoop,
    *,
    workspace_root: Path,
    config: OperatorConfig,
    enabled: bool,
    fallbacks: list[str] | None = None,
) -> OperatorConfig:
    patch_model_failover(enabled=enabled, fallbacks=fallbacks)
    updated = load_operator_config()
    primary = normalize_backend(config.model_backend, fallback=updated.model_backend)
    install_loop_model(
        loop,
        workspace_root=workspace_root,
        backend=primary,
        config=updated,
    )
    return updated


def format_settings_summary(config: OperatorConfig) -> str:
    chain = (
        " → ".join([config.model_backend, *config.model_fallbacks])
        if config.model_failover_enabled and config.model_fallbacks
        else "(none)"
    )
    return (
        f"model={config.model_backend} · failover="
        f"{'on' if config.model_failover_enabled else 'off'} · chain={chain}"
    )


def parse_slash_command(text: str) -> tuple[str, list[str]] | None:
    """Return ``(command, args)`` for supported slash input, else ``None``."""

    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.split()
    command = parts[0].lower()
    if command in {"/settings", "/help", "/?"}:
        return command, parts[1:]
    if command == "/failover" and parts[1:2]:
        return command, [parts[1].lower()]
    if command == "/model" and parts[1:2]:
        return command, [parts[1].lower()]
    return None
