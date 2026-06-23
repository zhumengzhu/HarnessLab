from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from harnesslab.artifact.in_memory import InMemoryArtifactStore
from harnesslab.artifact.sqlite_store import SqliteArtifactStore
from harnesslab.checkpoint.store import SqliteCheckpointStore, restore_snapshots
from harnesslab.core.budget import BudgetLimits
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.contracts import (
    ArtifactStorePort,
    MemoryStorePort,
    SessionStorePort,
    SpanRecorderPort,
)
from harnesslab.core.loop import DEFAULT_MAX_STEPS, HarnessLoop
from harnesslab.core.models import Session
from harnesslab.core.operator_config import (
    OperatorConfig,
    apply_provider_env,
    config_settings_snapshot,
    load_operator_config,
    resolve_model_backend,
    resolve_runtime_limits,
    resolve_shell_profile,
)
from harnesslab.core.prompt import (
    PromptBlock,
    build_agents_md_block,
    build_env_block,
    build_planning_block,
    build_skills_block,
    build_tool_guide_block,
)
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.skill_policy import (
    choose_skill_names,
    list_skills,
    selected_skills_from_messages,
)
from harnesslab.core.title import LiveTitleNamer
from harnesslab.core.tool_hooks import build_hook_runner
from harnesslab.eval.baseline import compare, load_baseline, save_baseline
from harnesslab.eval.loader import load_suite, load_task
from harnesslab.eval.report import render_stdout, write_json
from harnesslab.eval.runner import TaskRunner, _build_tool_registry
from harnesslab.eval.task import TaskResult, TaskSuite
from harnesslab.improve import (
    dedupe_against_existing,
    generate,
    write_proposal,
)
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.memory.semantic_sqlite import SqliteSemanticMemoryStore
from harnesslab.memory.sqlite_store import SqliteMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.providers.context_limits import align_runtime_limits_with_model
from harnesslab.providers.deepseek import tool_specs_from_registry
from harnesslab.providers.registry import create_model, normalize_backend
from harnesslab.replay import (
    UnreplayableTraceError,
    child_session_ids_for_parent,
    detect_divergence,
    group_by_session,
    read_spans,
    replay_session,
)
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.session.sqlite_store import SqliteSessionStore
from harnesslab.skills.catalog import (
    install_skill,
    install_skill_from_catalog,
    list_skill_records,
    remove_skill,
    search_skills,
)
from harnesslab.skills.index_loader import default_catalog_sources
from harnesslab.telemetry.aggregate import aggregate_spans, render_metrics
from harnesslab.telemetry.log import configure_logging, get_logger
from harnesslab.telemetry.recorder_factory import build_span_recorder, default_spans_path
from harnesslab.tools.fetch_url_tool import FetchUrlTool, resolve_jina_api_key
from harnesslab.tools.file_tools import (
    EditFileTool,
    GlobTool,
    GrepTool,
    ReadFileTool,
    WriteFileTool,
)
from harnesslab.tools.mcp_adapter import McpServerConfig, register_mcp_servers
from harnesslab.tools.patch import ApplyPatchTool
from harnesslab.tools.python_sandbox_tool import RunPythonSandboxedTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.research_tools import (
    HtmlToMarkdownTool,
    ReadPdfTool,
    WebSearchTool,
    resolve_web_search_api_key,
)
from harnesslab.tools.shell_tool import RunShellSafeTool
from harnesslab.tools.spawn_sub_agent import SpawnSubAgentTool
from harnesslab.tune import (
    DEFAULT_CONFIG,
    DEFAULT_SEARCH_SPACE,
    EvalObjective,
    TrialRecord,
    build_report,
    optimize,
    write_report,
)
from harnesslab.tune.prompt import (
    ModelCandidateGenerator,
    default_system_prompt,
    freeze_candidates,
    generation_composer,
    load_candidates,
    make_model_text_generator,
    run_prompt_tuning,
    write_prompt_report,
)
from harnesslab.web.server import WebRuntime, serve
from harnesslab.web.span_hub import SpanHub

StorageBackend = Literal["memory", "sqlite"]
ModelBackend = Literal["simple", "deepseek", "anthropic", "openai", "gemini"]

DEFAULT_SQLITE_PATH = ".harnesslab/state.sqlite"
DEFAULT_TASKS_DIR = "eval/tasks"
DEFAULT_BASELINE_PATH = "eval/baseline.json"
DEFAULT_REPORTS_DIR = "eval/reports"
DEFAULT_PROPOSALS_DIR = "proposals"
DEFAULT_MIN_OCCURRENCES = 2

SUBCOMMANDS = (
    "run",
    "eval",
    "replay",
    "metrics",
    "propose",
    "tune",
    "tune-prompt",
    "session",
    "artifact",
    "context",
    "serve",
    "skill",
    "check",
    "pricing",
    "tui",
)

DEFAULT_TUNE_N_INIT = 6
DEFAULT_TUNE_N_ITER = 12

EXIT_OK = 0
EXIT_UNREPLAYABLE = 2
EXIT_TASK_FAILED = 2
EXIT_REGRESSED = 3
EXIT_DIVERGED = 4
EXIT_USAGE = 64


def _load_operator_config() -> OperatorConfig:
    try:
        return load_operator_config()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _eval_skip_tags(args: argparse.Namespace) -> set[str]:
    tags: set[str] = set()
    if getattr(args, "skip_tags", None):
        tags.update(t.strip() for t in args.skip_tags.split(",") if t.strip())
    env = os.environ.get("HARNESSLAB_EVAL_SKIP_TAGS", "")
    if env.strip():
        tags.update(t.strip() for t in env.split(",") if t.strip())
    if os.environ.get("RUN_LIVE_EVAL") != "1":
        tags.add("network")
    return tags


def _filter_suite_by_tags(suite: TaskSuite, skip_tags: set[str]) -> TaskSuite:
    if not skip_tags:
        return suite
    kept = [t for t in suite.tasks if not skip_tags.intersection(t.tags)]
    return TaskSuite(tasks=kept)


def _env_int(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _budget_action(value: str) -> Literal["ask_user", "final", "error"]:
    normalized = value.strip().lower()
    if normalized not in {"ask_user", "final", "error"}:
        return "ask_user"
    return normalized  # type: ignore[return-value]


def _make_dynamic_blocks_provider(
    workspace_root: Path,
    tools: ToolRegistry,
    *,
    skill_selection_mode: Literal["heuristic", "model"] = "heuristic",
    planning_mode: Literal["off", "hint", "required"] = "off",
):
    """Build the per-call dynamic prompt blocks for DeepSeek.

    The provider is called once per model decision (inside
    :meth:`DeepSeekModel._request_body`). ``env`` and ``tool_guide``
    are always emitted; ``agents_md`` is only emitted when the
    workspace actually ships one.
    """

    def provider(_session: Session) -> list[PromptBlock]:
        blocks: list[PromptBlock] = [build_env_block(workspace_root)]
        agents = build_agents_md_block(workspace_root)
        if agents is not None:
            blocks.append(agents)
        planning = build_planning_block(planning_mode)
        if planning is not None:
            blocks.append(planning)
        available_skills = list_skills(workspace_root)
        pinned = selected_skills_from_messages(_session.messages)
        latest_user = ""
        for msg in reversed(_session.messages):
            if msg.role == "user":
                latest_user = msg.content
                break
        if skill_selection_mode == "model":
            selected = None
        else:
            selected = choose_skill_names(
                available=available_skills,
                pinned=pinned,
                user_input=latest_user,
                max_skills=3,
            )
        skills = build_skills_block(
            workspace_root,
            selected_names=selected,
            pinned_names=pinned,
        )
        if skills is not None:
            blocks.append(skills)
        blocks.append(build_tool_guide_block(tools.list()))
        return blocks

    return provider


def _build_stores(
    backend: StorageBackend,
    workspace_root: Path,
    sqlite_path: Path | None,
) -> tuple[SessionStorePort, MemoryStorePort]:
    if backend == "memory":
        return InMemorySessionStore(), InMemoryMemoryStore()
    if backend == "sqlite":
        db_path = sqlite_path or (workspace_root / DEFAULT_SQLITE_PATH)
        if not db_path.is_absolute():
            db_path = workspace_root / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteSessionStore(db_path), SqliteMemoryStore(db_path)
    raise ValueError(f"unknown storage backend: {backend}")


def _env_optional_float(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _build_checkpoint_store(
    backend: StorageBackend,
    workspace_root: Path,
    sqlite_path: Path | None,
) -> SqliteCheckpointStore | None:
    if backend != "sqlite":
        return None
    db_path = sqlite_path or (workspace_root / DEFAULT_SQLITE_PATH)
    if not db_path.is_absolute():
        db_path = workspace_root / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteCheckpointStore(db_path)


def _serve_settings_snapshot(
    config: OperatorConfig,
    *,
    workspace_root: Path,
    model_backend: str,
    loop: HarnessLoop,
) -> dict[str, Any]:
    """Settings payload for ``WebRuntime`` including runtime-only fields."""

    settings = config_settings_snapshot(
        config,
        workspace_root=workspace_root,
        model_backend=model_backend,
    )
    mcp_health = getattr(loop, "_mcp_health", None)
    if isinstance(mcp_health, dict):
        settings["mcp_health"] = mcp_health
    return settings


def _build_semantic_memory(
    backend: StorageBackend,
    workspace_root: Path,
    sqlite_path: Path | None,
) -> SqliteSemanticMemoryStore | None:
    if backend != "sqlite":
        return None
    db_path = sqlite_path or (workspace_root / DEFAULT_SQLITE_PATH)
    if not db_path.is_absolute():
        db_path = workspace_root / db_path
    return SqliteSemanticMemoryStore(db_path)


def _mcp_configs_from_operator(
    operator_config: OperatorConfig | None,
) -> tuple[McpServerConfig, ...]:
    if operator_config is None:
        return ()
    out: list[McpServerConfig] = []
    for item in operator_config.mcp_servers:
        out.append(
            McpServerConfig(
                name=str(item["name"]),
                command=str(item["command"]),
                args=tuple(item.get("args", ())),
                env_names=tuple(item.get("env_names", ())),
                policy_profile=str(item.get("policy_profile", "strict")),
                allowed_tools=frozenset(operator_config.mcp_allowed_tools),
            )
        )
    return tuple(out)


def _build_artifact_store(
    backend: StorageBackend,
    workspace_root: Path,
    sqlite_path: Path | None,
    *,
    enabled: bool,
) -> ArtifactStorePort | None:
    if not enabled:
        return None
    if backend == "memory":
        return InMemoryArtifactStore()
    if backend == "sqlite":
        db_path = sqlite_path or (workspace_root / DEFAULT_SQLITE_PATH)
        if not db_path.is_absolute():
            db_path = workspace_root / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteArtifactStore(db_path, workspace_root=workspace_root)
    raise ValueError(f"unknown storage backend: {backend}")


def build_runtime(
    workspace_root: Path,
    limits: RuntimeLimits | None = None,
    storage_backend: StorageBackend = "memory",
    sqlite_path: Path | None = None,
    model_backend: ModelBackend = "simple",
    spans: SpanRecorderPort | None = None,
    shell_profile: str | None = None,
    operator_config: OperatorConfig | None = None,
) -> HarnessLoop:
    limits = limits or RuntimeLimits()
    limits = align_runtime_limits_with_model(
        limits,
        backend=model_backend,
        config=operator_config,
    )
    env_artifact_threshold = _env_int("HARNESSLAB_ARTIFACT_THRESHOLD_BYTES", None)
    if env_artifact_threshold is not None:
        limits = replace(limits, artifact_threshold_bytes=env_artifact_threshold)
    effective_shell_profile = (
        shell_profile
        or (operator_config.shell_profile if operator_config is not None else None)
        or "dev"
    )
    # ``open`` is the new default; SSRF protection lives inside
    # ``validate_fetch_url`` so the loosened policy stays safe. Operators
    # can pin ``fetch_url.mode = "strict"`` to reintroduce the allowlist.
    fetch_mode = "open"
    if operator_config is not None and operator_config.fetch_url_mode != "auto":
        fetch_mode = operator_config.fetch_url_mode
    elif effective_shell_profile == "strict":
        fetch_mode = "strict"
    web_search_backend = (
        os.environ.get("WEB_SEARCH_BACKEND")
        or (operator_config.web_search_backend if operator_config is not None else None)
        or "duckduckgo"
    )
    try:
        web_search_max_results = int(
            os.environ.get(
                "WEB_SEARCH_MAX_RESULTS",
                str(
                    operator_config.web_search_max_results
                    if operator_config is not None
                    else 5
                ),
            )
        )
    except ValueError:
        web_search_max_results = (
            operator_config.web_search_max_results if operator_config is not None else 5
        )
    web_search_fallback_backend = (
        operator_config.web_search_fallback_backend
        if operator_config is not None
        else None
    )
    configured_api_key_env = (
        operator_config.web_search_api_key_env
        if operator_config is not None and operator_config.web_search_api_key_env
        else None
    )
    web_search_api_key = resolve_web_search_api_key(
        web_search_backend,
        configured_api_key_env,
    )

    # Memory store is wired into the loop for session-scoped notes (Phase 3.3).
    sessions, memory = _build_stores(storage_backend, workspace_root, sqlite_path)
    artifacts = _build_artifact_store(
        storage_backend,
        workspace_root,
        sqlite_path,
        enabled=bool(limits.artifact_threshold_bytes),
    )
    checkpoint_store = _build_checkpoint_store(storage_backend, workspace_root, sqlite_path)
    semantic_memory = _build_semantic_memory(storage_backend, workspace_root, sqlite_path)
    python_profile = (
        operator_config.python_sandbox_profile if operator_config is not None else "disabled"
    )
    if operator_config is not None and operator_config.limits.python_sandbox_profile != "disabled":
        python_profile = operator_config.limits.python_sandbox_profile
    mcp_allowed = frozenset(
        operator_config.mcp_allowed_tools if operator_config is not None else ()
    )
    multi_agent = bool(operator_config.multi_agent_enabled if operator_config else False)
    policy = DefaultPolicy(
        workspace_root=workspace_root,
        shell_profile=effective_shell_profile,
        fetch_url_mode=fetch_mode,
        fetch_url_allowlist=(
            frozenset(operator_config.fetch_url_allowlist)
            if operator_config is not None
            else None
        ),
        fetch_url_deny_hosts=(
            frozenset(operator_config.fetch_url_deny_hosts)
            if operator_config is not None
            else None
        ),
        mcp_allowed_tools=mcp_allowed,
        python_sandbox_profile=python_profile,
        enable_spawn_sub_agent=multi_agent,
    )
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace_root, limits=limits))
    tools.register(WriteFileTool(workspace_root, limits=limits))
    tools.register(EditFileTool(workspace_root, limits=limits))
    tools.register(ApplyPatchTool(workspace_root, limits=limits))
    tools.register(GrepTool(workspace_root, limits=limits))
    tools.register(GlobTool(workspace_root, limits=limits))
    tools.register(
        FetchUrlTool(
            limits=limits,
            mode=fetch_mode,
            host_allowlist=(
                frozenset(operator_config.fetch_url_allowlist)
                if operator_config is not None
                else None
            ),
            deny_hosts=(
                frozenset(operator_config.fetch_url_deny_hosts)
                if operator_config is not None
                else None
            ),
            provider=(
                operator_config.fetch_url_provider
                if operator_config is not None
                else "direct"
            ),
            jina_api_key=(
                resolve_jina_api_key(operator_config.fetch_url_jina_api_key_env)
                if operator_config is not None
                else resolve_jina_api_key(None)
            ),
        )
    )
    tools.register(
        WebSearchTool(
            backend=web_search_backend,
            fallback_backend=web_search_fallback_backend,
            max_results=web_search_max_results,
            api_key=web_search_api_key,
            configured_api_key_env=configured_api_key_env,
            api_base_url=(
                operator_config.web_search_api_base_url
                if operator_config is not None
                else None
            ),
        )
    )
    tools.register(HtmlToMarkdownTool(limits=limits))
    tools.register(ReadPdfTool(workspace_root, limits=limits))
    tools.register(RunShellSafeTool(workspace_root, limits=limits))
    if python_profile != "disabled":
        tools.register(RunPythonSandboxedTool(workspace_root, limits=limits))
    mcp_health: dict[str, dict] = {}
    mcp_configs = _mcp_configs_from_operator(operator_config)
    if mcp_configs:
        mcp_health = register_mcp_servers(tools, mcp_configs)
    loop_holder: list[HarnessLoop] = []
    if multi_agent:
        tools.register(
            SpawnSubAgentTool(
                lambda: loop_holder[0],
                max_depth=limits.max_sub_agent_depth,
                max_per_session=limits.max_sub_agents_per_session,
            )
        )
    if spans is None:
        spans = build_span_recorder(workspace_root)
    raw_skill_mode = (
        os.environ.get("HARNESSLAB_SKILL_SELECTION_MODE")
        or (
            operator_config.skill_selection_mode
            if operator_config is not None
            else "heuristic"
        )
    )
    effective_skill_mode: Literal["heuristic", "model"] = (
        "model" if str(raw_skill_mode).strip().lower() == "model" else "heuristic"
    )
    raw_planning_mode = (
        os.environ.get("HARNESSLAB_PLANNING_MODE")
        or (operator_config.planning_mode if operator_config is not None else "off")
    )
    mode_text = str(raw_planning_mode).strip().lower()
    effective_planning_mode: Literal["off", "hint", "required"] = (
        mode_text if mode_text in {"off", "hint", "required"} else "off"
    )
    raw_replan = os.environ.get("HARNESSLAB_REPLAN_AFTER_STEPS")
    if raw_replan is not None and raw_replan.strip():
        try:
            effective_replan_after_steps = int(raw_replan.strip())
        except ValueError:
            effective_replan_after_steps = None
    else:
        effective_replan_after_steps = (
            operator_config.replan_after_steps if operator_config is not None else None
        )
    budget_enabled_raw = os.environ.get("HARNESSLAB_BUDGET_ENABLED")
    if budget_enabled_raw is None:
        budget_enabled = operator_config.budget_enabled if operator_config is not None else False
    else:
        budget_enabled = budget_enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
    budget_limits = BudgetLimits(
        enabled=budget_enabled,
        soft_ratio=max(
            0.01,
            min(
                1.0,
                _env_float(
                    "HARNESSLAB_BUDGET_SOFT_RATIO",
                    operator_config.budget_soft_ratio if operator_config is not None else 0.8,
                ),
            ),
        ),
        action_on_hard=_budget_action(
            str(
                os.environ.get("HARNESSLAB_BUDGET_ACTION_ON_HARD")
                or (
                    operator_config.budget_action_on_hard
                    if operator_config is not None
                    else "ask_user"
                )
            )
        ),
        max_llm_calls_per_turn=_env_int(
            "HARNESSLAB_BUDGET_MAX_LLM_CALLS_PER_TURN",
            operator_config.budget_max_llm_calls_per_turn if operator_config else None,
        ),
        max_tool_calls_per_turn=_env_int(
            "HARNESSLAB_BUDGET_MAX_TOOL_CALLS_PER_TURN",
            operator_config.budget_max_tool_calls_per_turn if operator_config else None,
        ),
        max_turn_wall_time_ms=_env_int(
            "HARNESSLAB_BUDGET_MAX_TURN_WALL_TIME_MS",
            operator_config.budget_max_turn_wall_time_ms if operator_config else None,
        ),
        max_session_tokens_total=_env_int(
            "HARNESSLAB_BUDGET_MAX_SESSION_TOKENS_TOTAL",
            operator_config.budget_max_session_tokens_total if operator_config else None,
        ),
        max_session_tool_calls_total=_env_int(
            "HARNESSLAB_BUDGET_MAX_SESSION_TOOL_CALLS_TOTAL",
            operator_config.budget_max_session_tool_calls_total if operator_config else None,
        ),
        max_session_wall_time_ms_total=_env_int(
            "HARNESSLAB_BUDGET_MAX_SESSION_WALL_TIME_MS_TOTAL",
            operator_config.budget_max_session_wall_time_ms_total if operator_config else None,
        ),
        max_session_cost_usd_total=_env_optional_float(
            "HARNESSLAB_BUDGET_MAX_SESSION_COST_USD_TOTAL",
            operator_config.budget_max_session_cost_usd_total if operator_config else None,
        ),
    )
    hook_runner = build_hook_runner(
        operator_config.pre_tool_hooks if operator_config is not None else (),
        operator_config.post_tool_hooks if operator_config is not None else (),
    )
    backend = normalize_backend(model_backend)
    model = create_model(
        backend,
        config=operator_config,
        tool_specs_provider=lambda: tool_specs_from_registry(tools.list()),
        dynamic_blocks_provider=_make_dynamic_blocks_provider(
            workspace_root,
            tools,
            skill_selection_mode=effective_skill_mode,
            planning_mode=effective_planning_mode,
        ),
    )
    get_logger("cli").info(
        "runtime ready workspace=%s model=%s storage=%s",
        workspace_root,
        backend,
        storage_backend,
    )
    title_namer = LiveTitleNamer(model) if backend == "deepseek" else None
    loop = HarnessLoop(
        model=model,
        policy=policy,
        sessions=sessions,
        tools=tools,
        spans=spans,
        clock=SystemClock(),
        ids=UuidIdProvider(),
        limits=limits,
        title_namer=title_namer,
        memory=memory,
        artifacts=artifacts,
        checkpoint_store=checkpoint_store,
        semantic_memory=semantic_memory,
        workspace_root=workspace_root,
        replan_after_steps=effective_replan_after_steps,
        budget_limits=budget_limits,
        hook_runner=hook_runner,
    )
    if multi_agent:
        loop_holder.append(loop)
    loop._mcp_health = mcp_health  # type: ignore[attr-defined]
    return loop


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harnesslab",
        description="HarnessLab CLI — run a single turn or the eval suite.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        metavar="LEVEL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=(
            "Application log level (default: INFO, or env HARNESSLAB_LOG; "
            "WARNING under pytest)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=False, metavar="COMMAND")

    # ----- run -----
    run = sub.add_parser(
        "run",
        help="Run a single turn against the loop.",
        description="Run one turn of the harness loop with the given user input.",
    )
    run.add_argument("input", help="User input or `/tool <name> <json>` command.")
    run.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used by file and shell tools.",
    )
    run.add_argument(
        "--storage",
        default="memory",
        choices=["memory", "sqlite"],
        help="Backend for session and memory stores (default: memory).",
    )
    run.add_argument(
        "--sqlite-path",
        default=None,
        help=(
            "SQLite DB path. Relative paths resolve against --workspace-root. "
            f"Defaults to {DEFAULT_SQLITE_PATH!r} when --storage=sqlite."
        ),
    )
    run.add_argument(
        "--model",
        default=None,
        choices=["simple", "deepseek", "anthropic", "openai", "gemini"],
        help=(
            "Model backend for `run` (default: simple, or model.default_backend "
            "from ~/.config/harnesslab/config.json when set)."
        ),
    )
    run.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=(
            "Maximum decision steps inside the inner agent loop "
            f"(default: {DEFAULT_MAX_STEPS}). The loop stops earlier when "
            "the model returns a terminal decision (final or ask_user)."
        ),
    )

    # ----- eval -----
    ev = sub.add_parser(
        "eval",
        help="Run the eval task suite.",
        description=(
            "Run YAML eval tasks against the live loop and report results, "
            "optionally updating the baseline."
        ),
    )
    ev.add_argument(
        "--tasks-dir",
        default=DEFAULT_TASKS_DIR,
        help=f"Directory containing *.yaml tasks (default: {DEFAULT_TASKS_DIR}).",
    )
    ev.add_argument(
        "--task",
        default=None,
        help="Run a single task by file stem (e.g. 02_write_then_read).",
    )
    ev.add_argument(
        "--baseline",
        default=DEFAULT_BASELINE_PATH,
        help=f"Path to the baseline JSON (default: {DEFAULT_BASELINE_PATH}).",
    )
    ev.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite the baseline with the current run's results.",
    )
    ev.add_argument(
        "--reports-dir",
        default=DEFAULT_REPORTS_DIR,
        help=f"Where to write JSON reports (default: {DEFAULT_REPORTS_DIR}).",
    )
    ev.add_argument(
        "--skip-tags",
        default=None,
        help=(
            "Comma-separated task tags to skip (e.g. network). Also reads "
            "HARNESSLAB_EVAL_SKIP_TAGS."
        ),
    )

    # ----- replay -----
    rp = sub.add_parser(
        "replay",
        help="Replay a JSONL trace and report any divergence.",
        description=(
            "Re-drive the recorded loop using ReplayModel + FrozenClock "
            "and compare the new trace to the original."
        ),
    )
    rp.add_argument("trace", help="Path to a JSONL trace file.")
    rp.add_argument(
        "--session-id",
        default=None,
        help="Replay only this session id (default: replay every session in order).",
    )
    rp.add_argument(
        "--workspace",
        default=None,
        help=(
            "Workspace root to use during replay (default: a fresh tmp dir). "
            "Pass the original workspace when tools depend on filesystem "
            "state written by earlier sessions."
        ),
    )
    rp.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Compare byte-for-byte instead of the semantic default "
            "(ignore timestamps, normalize ids, ignore tool output text)."
        ),
    )
    rp.add_argument(
        "--include-children",
        action="store_true",
        help=(
            "With --session-id, also replay child sessions spawned from "
            "that parent (in trace order after the parent)."
        ),
    )

    # ----- metrics -----
    mt = sub.add_parser(
        "metrics",
        help="Aggregate counts and latency from a JSONL trace.",
    )
    mt.add_argument("trace", help="Path to a JSONL trace file.")
    mt.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human summary.",
    )

    # ----- propose -----
    pp = sub.add_parser(
        "propose",
        help="Generate advisory improvement proposals from failure clusters.",
        description=(
            "Build clusters from trace failures and/or eval failures, "
            "then write one markdown proposal per cluster. Proposals are "
            "advisory and are deduped against any open proposal already "
            "on disk."
        ),
    )
    pp.add_argument(
        "--trace",
        default=None,
        help="Path to a JSONL trace file to mine for failure events.",
    )
    pp.add_argument(
        "--eval-report",
        default=None,
        help=(
            "Path to an eval report JSON (e.g. eval/reports/latest.json) "
            "to mine for failed tasks."
        ),
    )
    pp.add_argument(
        "--out",
        default=DEFAULT_PROPOSALS_DIR,
        help=f"Directory to write proposals into (default: {DEFAULT_PROPOSALS_DIR}).",
    )
    pp.add_argument(
        "--min-occurrences",
        type=int,
        default=DEFAULT_MIN_OCCURRENCES,
        help=(
            f"Minimum occurrences per cluster to emit a proposal "
            f"(default: {DEFAULT_MIN_OCCURRENCES})."
        ),
    )
    pp.add_argument(
        "--format",
        default="md",
        choices=["md", "json"],
        help=(
            "md (default): write one markdown file per proposal under --out. "
            "json: emit a JSON array on stdout instead of touching disk."
        ),
    )

    # ----- tune -----
    tn = sub.add_parser(
        "tune",
        help="Bayesian search for a better runtime config (advisory).",
        description=(
            "Run deterministic Gaussian-process Bayesian optimization over "
            "runtime knobs (RuntimeLimits + shell profile), scored by the "
            "eval suite, and write an advisory config-diff proposal. No LLM, "
            "no RNG; the suggestion is never applied automatically."
        ),
    )
    tn.add_argument(
        "--tasks-dir",
        default=DEFAULT_TASKS_DIR,
        help=f"Directory containing *.yaml tasks (default: {DEFAULT_TASKS_DIR}).",
    )
    tn.add_argument(
        "--task",
        default=None,
        help="Tune against a single task by file stem (faster iteration).",
    )
    tn.add_argument(
        "--skip-tags",
        default=None,
        help="Comma-separated task tags to skip (also reads HARNESSLAB_EVAL_SKIP_TAGS).",
    )
    tn.add_argument(
        "--n-init",
        type=int,
        default=DEFAULT_TUNE_N_INIT,
        help=f"Initial space-filling evaluations (default: {DEFAULT_TUNE_N_INIT}).",
    )
    tn.add_argument(
        "--n-iter",
        type=int,
        default=DEFAULT_TUNE_N_ITER,
        help=f"Bayesian-optimization iterations (default: {DEFAULT_TUNE_N_ITER}).",
    )
    tn.add_argument(
        "--out",
        default=DEFAULT_PROPOSALS_DIR,
        help=f"Directory to write the tuning proposal into (default: {DEFAULT_PROPOSALS_DIR}).",
    )
    tn.add_argument(
        "--format",
        default="md",
        choices=["md", "json"],
        help=(
            "md (default): write a markdown config-diff proposal under --out. "
            "json: emit the report as JSON on stdout instead of touching disk."
        ),
    )

    # ----- tune-prompt -----
    tp = sub.add_parser(
        "tune-prompt",
        help="Benchmark LLM-generated prompt candidates (advisory, live model).",
        description=(
            "Bayesian self-evolution Layer B2: score already-frozen prompt "
            "candidates against a LIVE model benchmark (isolated from "
            "eval/replay), rank them by a Beta-Binomial success-rate posterior, "
            "and write an advisory prompt_tuning proposal. Candidates are "
            "produced (e.g. by an LLM) and frozen UPSTREAM into --candidates; "
            "this command only scores and ranks them. Never auto-applied."
        ),
    )
    tp.add_argument(
        "--candidates",
        default=None,
        help=(
            "Path to a frozen candidates JSON file (array of PromptCandidate). "
            "Mutually exclusive with --generate."
        ),
    )
    tp.add_argument(
        "--generate",
        default=None,
        metavar="INSTRUCTION",
        help=(
            "Generate candidates with the live model from this instruction "
            "(e.g. 'make the agent more concise'), freeze them, then benchmark. "
            "Mutually exclusive with --candidates."
        ),
    )
    tp.add_argument(
        "--n",
        type=int,
        default=4,
        help="Number of candidates to request when using --generate (default: 4).",
    )
    tp.add_argument(
        "--save-candidates",
        default=None,
        help=(
            "Where to freeze generated candidates (default: "
            "<--out>/prompt_candidates.json). Only used with --generate."
        ),
    )
    tp.add_argument(
        "--benchmark-dir",
        default=DEFAULT_TASKS_DIR,
        help=(
            "Directory of *.yaml benchmark tasks scored by final_reply_contains "
            f"(default: {DEFAULT_TASKS_DIR})."
        ),
    )
    tp.add_argument(
        "--task",
        default=None,
        help="Benchmark against a single task by file stem (faster iteration).",
    )
    tp.add_argument(
        "--skip-tags",
        default=None,
        help="Comma-separated task tags to skip (also reads HARNESSLAB_EVAL_SKIP_TAGS).",
    )
    tp.add_argument(
        "--model",
        default="deepseek",
        help=(
            "Live model backend for the benchmark (deepseek/anthropic/openai/"
            "gemini). 'simple' is rejected: it ignores the system prompt."
        ),
    )
    tp.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Times to run the suite per candidate to reduce benchmark noise.",
    )
    tp.add_argument(
        "--instruction",
        default=None,
        help="Optional note describing what the candidates were trying to improve.",
    )
    tp.add_argument(
        "--out",
        default=DEFAULT_PROPOSALS_DIR,
        help=f"Directory to write the prompt proposal into (default: {DEFAULT_PROPOSALS_DIR}).",
    )
    tp.add_argument(
        "--format",
        default="md",
        choices=["md", "json"],
        help=(
            "md (default): write a markdown prompt proposal under --out. "
            "json: emit the report as JSON on stdout instead of touching disk."
        ),
    )

    # ----- session -----
    se = sub.add_parser(
        "session",
        help="List, inspect, resume, or fork persisted sessions.",
        description=(
            "Operate on the persisted session store (SQLite). Use this "
            "to find a session id, inspect its lifecycle and conversation, "
            "continue work where it left off, or branch off a new session."
        ),
    )
    se.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to locate the SQLite store.",
    )
    se.add_argument(
        "--sqlite-path",
        default=None,
        help=(
            "SQLite DB path. Relative paths resolve against --workspace-root. "
            f"Defaults to {DEFAULT_SQLITE_PATH!r}."
        ),
    )
    se_sub = se.add_subparsers(
        dest="session_action",
        required=True,
        metavar="ACTION",
    )

    ls = se_sub.add_parser("ls", help="List sessions newest-first.")
    ls.add_argument("--limit", type=int, default=20, help="Max rows to print.")
    ls.add_argument(
        "--status",
        default=None,
        choices=["running", "waiting_user", "done", "failed", "aborted"],
        help="Restrict to sessions in this lifecycle state.",
    )

    sh = se_sub.add_parser("show", help="Show one session and its messages.")
    sh.add_argument("session_id")
    sh.add_argument(
        "--no-messages",
        action="store_true",
        help="Print metadata only (skip the conversation transcript).",
    )
    sh.add_argument(
        "--include-children",
        action="store_true",
        help="List child sessions spawned from this session (metadata only).",
    )

    rs = se_sub.add_parser("resume", help="Run another turn on an existing session.")
    rs.add_argument("session_id")
    rs.add_argument("input", help="The next user message for this session.")
    rs.add_argument(
        "--model",
        default="simple",
        choices=["simple", "deepseek", "anthropic", "openai", "gemini"],
        help="Model backend for the resumed turn (default: simple).",
    )
    rs.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help="Inner-loop step budget for the resumed turn.",
    )

    fk = se_sub.add_parser(
        "fork",
        help="Fork a session: copy messages, pin parent_session_id.",
    )
    fk.add_argument("session_id")
    fk.add_argument(
        "--goal",
        default=None,
        help="Override the goal/title of the new session (defaults to parent's).",
    )

    cp = se_sub.add_parser("checkpoints", help="List checkpoints for a session.")
    cp.add_argument("session_id")

    rw = se_sub.add_parser("rewind", help="Restore files from a checkpoint.")
    rw.add_argument("session_id")
    rw.add_argument("checkpoint_id")

    # ----- artifact -----
    ar = sub.add_parser(
        "artifact",
        help="List or show stored tool-output artifacts.",
    )
    ar.add_argument("--workspace-root", default=".", help="Workspace root.")
    ar.add_argument(
        "--sqlite-path",
        default=None,
        help=f"SQLite DB path (default: {DEFAULT_SQLITE_PATH!r}).",
    )
    ar_sub = ar.add_subparsers(dest="artifact_action", required=True, metavar="ACTION")
    ar_ls = ar_sub.add_parser("ls", help="List artifact metadata.")
    ar_ls.add_argument("--session-id", default=None, help="Filter by session id.")
    ar_ls.add_argument("--limit", type=int, default=20, help="Max rows.")
    ar_show = ar_sub.add_parser("show", help="Show artifact bytes (UTF-8).")
    ar_show.add_argument("artifact_id")

    sub.add_parser("tui", help="Launch the Textual terminal UI.")

    # ----- context -----
    ctx = sub.add_parser(
        "context",
        help="Inspect ContextSnapshots emitted by the loop.",
        description=(
            "Read a JSONL trace and surface the per-call ContextSnapshot "
            "data that the Phase 2.6 loop writes into model_call events. "
            "Useful for spotting context-window pressure before it "
            "triggers an emergency compaction."
        ),
    )
    ctx.add_argument("trace", help="Path to a JSONL trace file.")
    ctx_sub = ctx.add_subparsers(
        dest="context_action",
        required=True,
        metavar="ACTION",
    )

    cshow = ctx_sub.add_parser(
        "show",
        help="Show the latest snapshot in the trace (peak figures + last call).",
    )
    cshow.add_argument(
        "--session-id",
        default=None,
        help="Restrict to one session id (default: all sessions in the file).",
    )
    cshow.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human summary.",
    )

    cseries = ctx_sub.add_parser(
        "series",
        help="Print one row per model_call snapshot (chronological).",
    )
    cseries.add_argument(
        "--session-id",
        default=None,
        help="Restrict to one session id (default: all sessions).",
    )
    cseries.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of rows to print (newest last). Default 20.",
    )

    # ----- serve (Web UI) -----
    sv = sub.add_parser(
        "serve",
        help="Start the local Web chat UI (localhost only).",
        description=(
            "Bind a localhost HTTP server with a minimal chat interface. "
            "Uses the same HarnessLoop and SQLite session store as the CLI."
        ),
    )
    sv.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used by file and shell tools.",
    )
    sv.add_argument(
        "--host",
        default=None,
        help="Bind address (default: config serve.host or 127.0.0.1).",
    )
    sv.add_argument(
        "--port",
        type=int,
        default=None,
        help="TCP port (default: config serve.port or 8787).",
    )
    sv.add_argument(
        "--sqlite-path",
        default=None,
        help=(
            "SQLite DB path. Relative paths resolve against --workspace-root. "
            f"Defaults to {DEFAULT_SQLITE_PATH!r}."
        ),
    )
    sv.add_argument(
        "--model",
        default=None,
        choices=["simple", "deepseek", "anthropic", "openai", "gemini"],
        help="Model backend (default: config model.default_backend or deepseek).",
    )
    sv.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Default inner-loop step budget per message (default: config or 20).",
    )

    # ----- skill (Phase 7) -----
    sk = sub.add_parser(
        "skill",
        help="List, search, and install workspace skills.",
    )
    sk.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root containing skills/*.md.",
    )
    sk_sub = sk.add_subparsers(dest="skill_action", required=True, metavar="ACTION")
    sk_sub.add_parser("list", help="List workspace and user-global skills.")
    sk_search = sk_sub.add_parser("search", help="Search skills by name/description/tags.")
    sk_search.add_argument("query", help="Case-insensitive substring query.")
    sk_install = sk_sub.add_parser("install", help="Install a skill markdown file.")
    sk_install.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Path to a .md skill file (omit when using --catalog-id).",
    )
    sk_install.add_argument(
        "--catalog-id",
        default=None,
        help="Install from a configured catalog index by skill id.",
    )
    sk_install.add_argument(
        "--scope",
        choices=["workspace", "user"],
        default="workspace",
        help="Install target directory (default: workspace/skills).",
    )
    sk_remove = sk_sub.add_parser("remove", help="Remove an installed skill.")
    sk_remove.add_argument("name", help="Skill name (markdown stem).")
    sk_remove.add_argument(
        "--scope",
        choices=["workspace", "user"],
        default="workspace",
        help="Remove from workspace or user skills directory.",
    )

    # ----- check (diagnostics) -----
    ck = sub.add_parser(
        "check",
        help="Run HarnessLab diagnostics.",
    )
    ck_sub = ck.add_subparsers(dest="check_action", required=True, metavar="ACTION")
    ck_net = ck_sub.add_parser(
        "network",
        help="Probe proxy env, web_search backend, and sample fetch_url targets.",
    )
    ck_net.add_argument(
        "--env-file",
        default=None,
        help="Dotenv file to load before checks (default: ~/.config/harnesslab/env).",
    )
    ck_net.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds (default: 20).",
    )

    # ----- pricing (catalog audit) -----
    pr = sub.add_parser(
        "pricing",
        help="Inspect pricing catalog coverage and fingerprint.",
    )
    pr_sub = pr.add_subparsers(dest="pricing_action", required=True, metavar="ACTION")
    pr_audit = pr_sub.add_parser(
        "audit",
        help="Compare model catalog entries to pricing schedules.",
    )
    pr_audit.add_argument(
        "--currency",
        default="USD",
        help="Currency to audit (default: USD).",
    )
    pr_sub.add_parser(
        "fingerprint",
        help="Print pricing catalog fingerprint and version.",
    )

    return parser


def _maybe_legacy_usage_hint() -> int | None:
    """Detect pre-Step-4 invocation style (`harnesslab "<input>"`) and emit
    a structured migration hint instead of a confusing argparse error."""
    if len(sys.argv) < 2:
        return None
    first = sys.argv[1]
    if first.startswith("-") or first in SUBCOMMANDS:
        return None
    print(
        "HarnessLab now uses subcommands.\n"
        f"  Did you mean: harnesslab run {first!r}\n"
        "  See `harnesslab --help` for the full command list.",
        file=sys.stderr,
    )
    return EXIT_USAGE


def main() -> None:
    legacy_exit = _maybe_legacy_usage_hint()
    if legacy_exit is not None:
        sys.exit(legacy_exit)

    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(getattr(args, "log_level", None))
    cli_log = get_logger("cli")
    if args.command:
        cli_log.debug("subcommand=%s", args.command)

    if args.command == "run":
        sys.exit(_cmd_run(args))
    if args.command == "eval":
        sys.exit(_cmd_eval(args))
    if args.command == "replay":
        sys.exit(_cmd_replay(args))
    if args.command == "metrics":
        sys.exit(_cmd_metrics(args))
    if args.command == "propose":
        sys.exit(_cmd_propose(args))
    if args.command == "tune":
        sys.exit(_cmd_tune(args))
    if args.command == "tune-prompt":
        sys.exit(_cmd_tune_prompt(args))
    if args.command == "session":
        sys.exit(_cmd_session(args))
    if args.command == "artifact":
        sys.exit(_cmd_artifact(args))
    if args.command == "context":
        sys.exit(_cmd_context(args))
    if args.command == "serve":
        sys.exit(_cmd_serve(args))
    if args.command == "skill":
        sys.exit(_cmd_skill(args))
    if args.command == "check":
        sys.exit(_cmd_check(args))
    if args.command == "pricing":
        sys.exit(_cmd_pricing(args))
    if args.command == "tui":
        sys.exit(_cmd_tui(args))

    parser.print_help(sys.stderr)
    sys.exit(EXIT_USAGE)


def _cmd_check(args: argparse.Namespace) -> int:
    if args.check_action == "network":
        from harnesslab.core.env_file import apply_env_file, env_file_path
        from harnesslab.diagnostics.network_check import (
            format_network_report,
            network_check_exit_code,
            run_network_checks,
        )

        env_path = Path(args.env_file).expanduser() if args.env_file else env_file_path()
        loaded = apply_env_file(env_path)
        if loaded is not None:
            print(f"Loaded env: {loaded}")
        lines = run_network_checks(timeout_seconds=args.timeout)
        print(format_network_report(lines))
        return network_check_exit_code(lines)
    print("Unknown check action.", file=sys.stderr)
    return EXIT_USAGE


def _cmd_pricing(args: argparse.Namespace) -> int:
    from harnesslab.providers.pricing import (
        audit_pricing_catalog,
        catalog_fingerprint,
        format_audit_report,
        load_pricing_catalog,
    )

    if args.pricing_action == "fingerprint":
        catalog = load_pricing_catalog()
        print(f"pricing_version: {catalog.pricing_version}")
        print(f"fingerprint: {catalog_fingerprint()}")
        return EXIT_OK
    if args.pricing_action == "audit":
        report = audit_pricing_catalog(currency=args.currency)
        print(format_audit_report(report))
        return EXIT_OK if not report.get("missing_model_ids") else EXIT_TASK_FAILED
    print("Unknown pricing action.", file=sys.stderr)
    return EXIT_USAGE


def _cmd_skill(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    config = _load_operator_config()
    catalog_sources = default_catalog_sources(config.skill_catalog_sources)
    if args.skill_action == "list":
        records = list_skill_records(
            workspace_root,
            catalog_sources=catalog_sources,
            include_catalog=True,
        )
        if not records:
            print("(no skills)")
            return EXIT_OK
        for record in records:
            tags = f" [{', '.join(record.tags)}]" if record.tags else ""
            print(f"{record.name}\t{record.scope}{tags}\t{record.description}")
        return EXIT_OK
    if args.skill_action == "search":
        records = search_skills(workspace_root, args.query, catalog_sources=catalog_sources)
        if not records:
            print("(no matches)")
            return EXIT_OK
        for record in records:
            tags = f" [{', '.join(record.tags)}]" if record.tags else ""
            print(f"{record.name}\t{record.scope}{tags}\t{record.description}")
        return EXIT_OK
    if args.skill_action == "remove":
        try:
            removed = remove_skill(workspace_root, args.name, scope=args.scope)
        except (FileNotFoundError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE
        print(f"removed: {removed}")
        return EXIT_OK
    catalog_id = getattr(args, "catalog_id", None)
    if catalog_id:
        try:
            dest = install_skill_from_catalog(
                workspace_root,
                catalog_id,
                scope=args.scope,
                catalog_sources=catalog_sources,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE
        print(f"installed: {dest}")
        return EXIT_OK
    if not args.source:
        print("install requires source path or --catalog-id", file=sys.stderr)
        return EXIT_USAGE
    try:
        dest = install_skill(workspace_root, Path(args.source), scope=args.scope)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    print(f"installed: {dest}")
    return EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    if args.max_steps < 1:
        print(
            f"--max-steps must be >= 1, got {args.max_steps}",
            file=sys.stderr,
        )
        return EXIT_USAGE
    config = _load_operator_config()
    apply_provider_env(config)
    try:
        loop = build_runtime(
            workspace_root=workspace_root,
            storage_backend=args.storage,
            sqlite_path=sqlite_path,
            model_backend=resolve_model_backend(
                args.model, config=config, fallback="simple"
            ),  # type: ignore[arg-type]
            limits=resolve_runtime_limits(None, config=config),
            shell_profile=resolve_shell_profile(None, config=config),
            operator_config=config,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    session = loop.start(goal=args.input)
    response = loop.run_session(session.id, args.input, max_steps=args.max_steps)
    print(response)
    return EXIT_OK


def _cmd_serve(args: argparse.Namespace) -> int:
    config = _load_operator_config()
    apply_provider_env(config)
    host = args.host or config.serve_host
    port = args.port if args.port is not None else config.serve_port
    max_steps = args.max_steps if args.max_steps is not None else config.serve_max_steps
    model_backend = resolve_model_backend(
        args.model, config=config, fallback="deepseek"
    )
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "Refusing to bind to a non-local address. "
            "HarnessLab serve is localhost-only.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if max_steps < 1:
        print(f"--max-steps must be >= 1, got {max_steps}", file=sys.stderr)
        return EXIT_USAGE
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    spans_path = default_spans_path(workspace_root)
    span_hub = SpanHub(build_span_recorder(workspace_root, spans_path=spans_path))
    try:
        loop = build_runtime(
            workspace_root=workspace_root,
            storage_backend="sqlite",
            sqlite_path=sqlite_path,
            model_backend=model_backend,  # type: ignore[arg-type]
            spans=span_hub,
            limits=resolve_runtime_limits(None, config=config),
            shell_profile=resolve_shell_profile(None, config=config),
            operator_config=config,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    runtime = WebRuntime(
        loop=loop,
        model_backend=model_backend,  # type: ignore[arg-type]
        workspace_root=workspace_root,
        default_max_steps=max_steps,
        span_hub=span_hub,
        spans_path=spans_path,
        operator_config=config,
        settings=_serve_settings_snapshot(
            config,
            workspace_root=workspace_root,
            model_backend=model_backend,
            loop=loop,
        ),
    )
    serve(runtime, host=host, port=port)
    return EXIT_OK


def _cmd_eval(args: argparse.Namespace) -> int:
    tasks_dir = Path(args.tasks_dir)
    baseline_path = Path(args.baseline)
    reports_dir = Path(args.reports_dir)

    suite = _load_suite_or_single(tasks_dir, args.task)
    suite = _filter_suite_by_tags(suite, _eval_skip_tags(args))
    results = TaskRunner().run(suite)

    if args.update_baseline:
        save_baseline(baseline_path, results)
        print(f"baseline updated: {baseline_path} ({len(results)} task(s))")
        return EXIT_OK

    baseline = load_baseline(baseline_path)
    regressions = compare(results, baseline)

    print(render_stdout(results, regressions))
    write_json(reports_dir / "latest.json", results, regressions)

    if regressions:
        return EXIT_REGRESSED
    if any(not r.passed for r in results):
        return EXIT_TASK_FAILED
    return EXIT_OK


def _load_suite_or_single(tasks_dir: Path, task_stem: str | None) -> TaskSuite:
    if task_stem is None:
        return load_suite(tasks_dir)
    task_path = tasks_dir / f"{task_stem}.yaml"
    if not task_path.exists():
        raise SystemExit(f"task file not found: {task_path}")
    return TaskSuite(tasks=[load_task(task_path)])


def _cmd_replay(args: argparse.Namespace) -> int:
    spans_path = Path(args.trace)
    if not spans_path.exists():
        raise SystemExit(f"spans file not found: {spans_path}")
    try:
        spans = read_spans(spans_path)
    except json.JSONDecodeError as exc:
        print(f"invalid JSONL spans: {exc}", file=sys.stderr)
        return EXIT_UNREPLAYABLE

    grouped = group_by_session(spans)
    if args.session_id is not None:
        if args.session_id not in grouped:
            print(
                f"session id {args.session_id!r} not found in spans "
                f"(present: {list(grouped.keys())})",
                file=sys.stderr,
            )
            return EXIT_UNREPLAYABLE
        session_ids = [args.session_id]
        if args.include_children:
            session_ids.extend(
                sid
                for sid in child_session_ids_for_parent(spans, args.session_id)
                if sid in grouped
            )
        grouped = {sid: grouped[sid] for sid in session_ids}

    workspace_root = Path(args.workspace).resolve() if args.workspace else None

    any_divergence = False
    ignore = frozenset({"sub_agent.run"})
    for sid, session_spans in grouped.items():
        try:
            replayed = replay_session(session_spans, workspace_root=workspace_root)
        except UnreplayableTraceError as exc:
            print(f"[{sid}] unreplayable: {exc}", file=sys.stderr)
            return EXIT_UNREPLAYABLE
        use_ignore = (
            ignore
            if any(s.name == "sub_agent.run" for s in session_spans)
            else frozenset()
        )
        report = detect_divergence(
            session_spans,
            replayed,
            strict=args.strict,
            ignore_span_names=use_ignore,
        )
        print(f"[{sid}] {report.render()}")
        if not report.matched:
            any_divergence = True

    return EXIT_DIVERGED if any_divergence else EXIT_OK


def _cmd_metrics(args: argparse.Namespace) -> int:
    spans_path = Path(args.trace)
    if not spans_path.exists():
        raise SystemExit(f"spans file not found: {spans_path}")
    try:
        spans = read_spans(spans_path)
    except json.JSONDecodeError as exc:
        print(f"invalid JSONL spans: {exc}", file=sys.stderr)
        return EXIT_USAGE

    metrics = aggregate_spans(spans)
    if args.json:
        print(json.dumps(metrics.model_dump(mode="json"), indent=2))
    else:
        print(render_metrics(metrics))
    return EXIT_OK


def _cmd_propose(args: argparse.Namespace) -> int:
    if not args.trace and not args.eval_report:
        print(
            "propose requires at least one of --trace or --eval-report",
            file=sys.stderr,
        )
        return EXIT_USAGE

    spans_list: list = []
    if args.trace:
        spans_path = Path(args.trace)
        if not spans_path.exists():
            raise SystemExit(f"spans file not found: {spans_path}")
        try:
            spans_list = read_spans(spans_path)
        except json.JSONDecodeError as exc:
            print(f"invalid JSONL spans: {exc}", file=sys.stderr)
            return EXIT_USAGE

    eval_results: list[TaskResult] | None = None
    if args.eval_report:
        report_path = Path(args.eval_report)
        if not report_path.exists():
            raise SystemExit(f"eval report not found: {report_path}")
        eval_results = _load_eval_results(report_path)

    out_dir = Path(args.out)
    proposals = generate(
        spans_list,
        eval_results=eval_results,
        min_occurrences=args.min_occurrences,
    )

    if args.format == "md":
        proposals = dedupe_against_existing(proposals, out_dir)

    if not proposals:
        print(
            "no new proposals "
            "(no clusters reached --min-occurrences, "
            "or all signatures already have an open proposal on disk)"
        )
        return EXIT_OK

    if args.format == "json":
        print(
            json.dumps(
                [p.model_dump(mode="json") for p in proposals],
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_OK

    for proposal in proposals:
        path = write_proposal(proposal, out_dir)
        print(f"wrote {path}  [{proposal.kind} x{proposal.occurrences}]")
    return EXIT_OK


def _load_eval_results(report_path: Path) -> list[TaskResult]:
    """Parse the JSON written by harnesslab.eval.report.write_json."""

    data = json.loads(report_path.read_text(encoding="utf-8"))
    raw_results = data.get("results", [])
    if not isinstance(raw_results, list):
        raise SystemExit(
            f"eval report missing 'results' list: {report_path}"
        )
    return [TaskResult.model_validate(r) for r in raw_results]


# ---------------------------------------------------------------------------
# tune subcommand (Bayesian config search, advisory)
# ---------------------------------------------------------------------------


def _cmd_tune(args: argparse.Namespace) -> int:
    tasks_dir = Path(args.tasks_dir)
    suite = _load_suite_or_single(tasks_dir, args.task)
    suite = _filter_suite_by_tags(suite, _eval_skip_tags(args))
    if not suite.tasks:
        print("no tasks to tune against (all filtered out)", file=sys.stderr)
        return EXIT_USAGE

    objective = EvalObjective(suite)
    result = optimize(
        DEFAULT_SEARCH_SPACE,
        objective,
        default_config=DEFAULT_CONFIG,
        n_init=args.n_init,
        n_iter=args.n_iter,
    )

    trials = [
        TrialRecord(
            config=config,
            cost=cost,
            breakdown=objective.breakdown(config).as_dict(),
        )
        for config, cost in result.trials
    ]
    report = build_report(
        objective=(
            "weighted cost = 100*failed_tasks + 5*tool_failures "
            "+ 5*invalid_args + 1*denials + 0.1*tool_calls (minimize)"
        ),
        default_config=DEFAULT_CONFIG,
        default_breakdown=objective.breakdown(DEFAULT_CONFIG).as_dict(),
        best_config=result.best_config,
        best_breakdown=objective.breakdown(result.best_config).as_dict(),
        trials=trials,
        dimensions=DEFAULT_SEARCH_SPACE.names,
    )

    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return EXIT_OK

    path = write_report(report, Path(args.out))
    verdict = "improved" if report.improved else "no improvement over default"
    print(
        f"wrote {path}  [{verdict}: cost "
        f"{report.default_cost:.4f} -> {report.best_cost:.4f}, "
        f"{len(report.trials)} evals]"
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# tune-prompt subcommand (Bayesian Layer B2: live-model prompt benchmark)
# ---------------------------------------------------------------------------


def _cmd_tune_prompt(args: argparse.Namespace) -> int:
    if bool(args.candidates) == bool(args.generate):
        print(
            "pass exactly one of --candidates (frozen file) or --generate "
            "(live LLM generation)",
            file=sys.stderr,
        )
        return EXIT_USAGE

    backend = normalize_backend(args.model)
    if backend == "simple":
        print(
            "tune-prompt needs a live model: SimpleModel ignores the system "
            "prompt so it cannot distinguish candidates. Pass "
            "--model deepseek/anthropic/openai/gemini.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if args.repeats < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return EXIT_USAGE

    config = _load_operator_config()

    if args.generate:
        if args.n < 1:
            print("--n must be >= 1", file=sys.stderr)
            return EXIT_USAGE
        candidates = _generate_prompt_candidates(
            backend=backend, config=config, instruction=args.generate, n=args.n
        )
        if not candidates:
            print(
                "candidate generation produced no usable candidates "
                "(model returned no valid JSON array)",
                file=sys.stderr,
            )
            return EXIT_USAGE
        save_path = Path(
            args.save_candidates or (Path(args.out) / "prompt_candidates.json")
        )
        freeze_candidates(candidates, save_path)
        print(f"generated {len(candidates)} candidate(s) -> {save_path}")
    else:
        candidates_path = Path(args.candidates)
        if not candidates_path.exists():
            print(f"candidates file not found: {candidates_path}", file=sys.stderr)
            return EXIT_USAGE
        try:
            candidates = load_candidates(candidates_path)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"failed to load candidates: {exc}", file=sys.stderr)
            return EXIT_USAGE
        if not candidates:
            print("candidates file is empty", file=sys.stderr)
            return EXIT_USAGE

    tasks_dir = Path(args.benchmark_dir)
    suite = _load_suite_or_single(tasks_dir, args.task)
    suite = _filter_suite_by_tags(suite, _eval_skip_tags(args))
    if not suite.tasks:
        print("no benchmark tasks (all filtered out)", file=sys.stderr)
        return EXIT_USAGE

    tmp_workspace = Path(tempfile.mkdtemp(prefix="hl-tune-prompt-"))
    tool_specs = tool_specs_from_registry(
        _build_tool_registry(tmp_workspace, RuntimeLimits()).list()
    )

    def factory(candidate):
        return create_model(
            backend,
            config=config,
            composer=candidate.composer(),
            tool_specs_provider=lambda: tool_specs,
            dynamic_blocks_provider=lambda _session: [],
        )

    report = run_prompt_tuning(
        candidates=candidates,
        suite=suite,
        model_factory=factory,
        instruction=args.instruction or args.generate or "",
        repeats=args.repeats,
    )

    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return EXIT_OK

    path = write_prompt_report(report, Path(args.out))
    verdict = "improved" if report.improved else "no improvement over baseline"
    print(f"wrote {path}  [{verdict}; best={report.best_id}]")
    return EXIT_OK


def _generate_prompt_candidates(
    *,
    backend: str,
    config: OperatorConfig,
    instruction: str,
    n: int,
):
    """Ask the live model for ``n`` candidate system prompts (frozen upstream).

    The generation model is built with **empty tool specs** and a neutral
    generation system prompt so it answers with the requested JSON array
    instead of trying to act as the agent under test.
    """

    gen_model = create_model(
        backend,
        config=config,
        composer=generation_composer(),
        tool_specs_provider=lambda: [],
        dynamic_blocks_provider=lambda _session: [],
    )
    generator = ModelCandidateGenerator(make_model_text_generator(gen_model))
    return generator.generate(
        base_prompt=default_system_prompt(), instruction=instruction, n=n
    )


# ---------------------------------------------------------------------------
# session subcommand
# ---------------------------------------------------------------------------


def _cmd_session(args: argparse.Namespace) -> int:
    if args.session_action == "ls":
        return _cmd_session_ls(args)
    if args.session_action == "show":
        return _cmd_session_show(args)
    if args.session_action == "resume":
        return _cmd_session_resume(args)
    if args.session_action == "fork":
        return _cmd_session_fork(args)
    if args.session_action == "checkpoints":
        return _cmd_session_checkpoints(args)
    if args.session_action == "rewind":
        return _cmd_session_rewind(args)
    print(f"unknown session action: {args.session_action}", file=sys.stderr)
    return EXIT_USAGE


def _cmd_session_ls(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    sessions, _ = _build_stores("sqlite", workspace_root, sqlite_path)
    rows = sessions.list(limit=args.limit, status=args.status)
    if not rows:
        print("(no sessions)")
        return EXIT_OK
    print(_format_session_table(rows))
    return EXIT_OK


def _cmd_session_show(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    sessions, _ = _build_stores("sqlite", workspace_root, sqlite_path)
    try:
        session = sessions.get(args.session_id)
    except KeyError:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return EXIT_USAGE
    print(_format_session_detail(session, include_messages=not args.no_messages))
    if args.include_children:
        children = sessions.list(parent_session_id=args.session_id, limit=50)
        print("")
        print(f"Children ({len(children)}):")
        if not children:
            print("  (none)")
        else:
            for child in children:
                title = child.title or child.goal
                print(
                    f"  {child.id}  status={child.status}  steps={child.step_count}  "
                    f"tokens={child.budget_usage.tokens_total}  "
                    f"cost_usd={child.budget_usage.cost_usd_total:.6f}  "
                    f"{title[:48]}"
                )
    return EXIT_OK


def _cmd_session_resume(args: argparse.Namespace) -> int:
    if args.max_steps < 1:
        print(
            f"--max-steps must be >= 1, got {args.max_steps}", file=sys.stderr
        )
        return EXIT_USAGE
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    try:
        loop = build_runtime(
            workspace_root=workspace_root,
            storage_backend="sqlite",
            sqlite_path=sqlite_path,
            model_backend=args.model,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        loop._sessions.get(args.session_id)  # type: ignore[attr-defined]
    except KeyError:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return EXIT_USAGE
    response = loop.run_session(args.session_id, args.input, max_steps=args.max_steps)
    print(response)
    return EXIT_OK


def _cmd_session_fork(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    loop = build_runtime(
        workspace_root=workspace_root,
        storage_backend="sqlite",
        sqlite_path=sqlite_path,
        model_backend="simple",
    )
    try:
        forked = loop.fork(args.session_id, goal=args.goal)
    except KeyError:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return EXIT_USAGE
    print(forked.id)
    return EXIT_OK


def _cmd_session_checkpoints(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    store = _build_checkpoint_store("sqlite", workspace_root, sqlite_path)
    if store is None:
        print("checkpoints require sqlite storage", file=sys.stderr)
        return EXIT_USAGE
    try:
        rows = store.list(args.session_id)
        if not rows:
            print("(no checkpoints)")
            return EXIT_OK
        for row in rows:
            print(f"{row.id}\t{row.tool_name}\t{row.created_at.isoformat()}")
        return EXIT_OK
    finally:
        store.close()


def _cmd_session_rewind(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    store = _build_checkpoint_store("sqlite", workspace_root, sqlite_path)
    if store is None:
        print("rewind requires sqlite storage", file=sys.stderr)
        return EXIT_USAGE
    try:
        checkpoint = store.get(args.checkpoint_id)
        if checkpoint.session_id != args.session_id:
            print("checkpoint does not belong to session", file=sys.stderr)
            return EXIT_USAGE
        touched = restore_snapshots(workspace_root, checkpoint.snapshots)
        print(f"restored {len(touched)} path(s): {', '.join(touched)}")
        return EXIT_OK
    except KeyError:
        print(f"checkpoint not found: {args.checkpoint_id}", file=sys.stderr)
        return EXIT_USAGE
    finally:
        store.close()


def _cmd_tui(args: argparse.Namespace) -> int:
    try:
        from harnesslab.tui.app import run_tui
    except ImportError as exc:
        print(f"TUI requires textual: {exc}", file=sys.stderr)
        return EXIT_USAGE
    workspace_root = Path(getattr(args, "workspace_root", ".")).resolve()
    run_tui(workspace_root)
    return EXIT_OK


def _artifact_store_for_cli(args: argparse.Namespace) -> SqliteArtifactStore:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    db_path = sqlite_path or (workspace_root / DEFAULT_SQLITE_PATH)
    if not db_path.is_absolute():
        db_path = workspace_root / db_path
    return SqliteArtifactStore(db_path, workspace_root=workspace_root)


def _cmd_artifact(args: argparse.Namespace) -> int:
    store = _artifact_store_for_cli(args)
    try:
        if args.artifact_action == "ls":
            rows = store.list(session_id=args.session_id, limit=args.limit)
            if not rows:
                print("(no artifacts)")
                return EXIT_OK
            for meta in rows:
                print(
                    f"{meta.id}\t{meta.session_id}\t{meta.mime}\t"
                    f"{meta.size_bytes}\t{meta.created_at.isoformat()}"
                )
            return EXIT_OK
        if args.artifact_action == "show":
            data = store.get(args.artifact_id)
            print(data.decode("utf-8", errors="replace"))
            return EXIT_OK
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    finally:
        store.close()
    return EXIT_USAGE


def _format_session_table(sessions) -> str:
    header = (
        "ID",
        "STATUS",
        "STEPS",
        "TURNS",
        "TOKENS",
        "BUDGET",
        "PARENT",
        "CREATED",
        "TITLE",
    )
    rows = [header]
    for s in sessions:
        parent = s.parent_session_id or "–"
        rows.append(
            (
                s.id,
                s.status,
                str(s.step_count),
                str(s.turn_count),
                str(s.budget_usage.tokens_total),
                s.budget_usage.last_budget_status,
                parent,
                s.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                (s.title or s.goal)[:60],
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = []
    for row in rows:
        lines.append(
            "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        )
    return "\n".join(lines)


def _format_session_detail(session, *, include_messages: bool) -> str:
    parent = session.parent_session_id or "(none)"
    last_step = session.last_step_at.isoformat() if session.last_step_at else "(never)"
    lines = [
        f"Session:   {session.id}",
        f"Title:     {session.title or '(none)'}",
        f"Goal:      {session.goal}",
        f"Status:    {session.status}",
        f"Turns:     {session.turn_count}",
        f"Steps:     {session.step_count}",
        f"Created:   {session.created_at.isoformat()}",
        f"Last step: {last_step}",
        f"Parent:    {parent}",
        "Budget:",
        f"  status:   {session.budget_usage.last_budget_status}",
        f"  llm_calls:{session.budget_usage.llm_calls_total}",
        f"  tools:    {session.budget_usage.tool_calls_total}",
        f"  tokens:   {session.budget_usage.tokens_total}",
        f"  wall_ms:  {session.budget_usage.wall_time_ms_total}",
        f"  cost_usd: {session.budget_usage.cost_usd_total:.6f}",
    ]
    if include_messages:
        lines.append("")
        lines.append(f"Messages ({len(session.messages)}):")
        for i, msg in enumerate(session.messages):
            preview = msg.content if len(msg.content) <= 120 else msg.content[:117] + "..."
            lines.append(f"  [{i}] {msg.role}: {preview}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# context subcommand: surface ContextSnapshot data from a trace
# ---------------------------------------------------------------------------


def _cmd_context(args: argparse.Namespace) -> int:
    if args.context_action == "show":
        return _cmd_context_show(args)
    if args.context_action == "series":
        return _cmd_context_series(args)
    print(f"unknown context action: {args.context_action}", file=sys.stderr)
    return EXIT_USAGE


def _cmd_context_show(args: argparse.Namespace) -> int:
    spans = _read_spans_or_exit(args.trace)
    snapshots = _collect_context_snapshots(spans, args.session_id)
    if not snapshots:
        msg = "(no llm.generate spans with context found"
        if args.session_id:
            msg += f" for session {args.session_id!r}"
        print(msg + ")")
        return EXIT_OK

    last = snapshots[-1]
    peak_conv = max(s["conversation_tokens"] for s in snapshots)
    peak_usage = max(s["usage_ratio"] for s in snapshots)
    summary = {
        "session_filter": args.session_id,
        "model_calls_with_context": len(snapshots),
        "peak_conversation_tokens": peak_conv,
        "peak_usage_ratio": round(peak_usage, 4),
        "latest": last,
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(_format_context_show(summary))
    return EXIT_OK


def _cmd_context_series(args: argparse.Namespace) -> int:
    spans = _read_spans_or_exit(args.trace)
    snapshots = _collect_context_snapshots(spans, args.session_id)
    if not snapshots:
        print("(no llm.generate spans with context found)")
        return EXIT_OK
    rows = snapshots[-max(1, args.limit) :]
    print(_format_context_series(rows))
    return EXIT_OK


def _read_spans_or_exit(spans_arg: str) -> list:
    spans_path = Path(spans_arg)
    if not spans_path.exists():
        raise SystemExit(f"spans file not found: {spans_path}")
    try:
        return read_spans(spans_path)
    except json.JSONDecodeError as exc:
        print(f"invalid JSONL spans: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from exc


def _collect_context_snapshots(
    spans: list,
    session_id: str | None,
) -> list[dict]:
    """Return one ``{session_id, created_at, **snapshot}`` row per LLM call."""

    from harnesslab.telemetry.span_attributes import SPAN_LLM_GENERATE

    rows: list[dict] = []
    for span in spans:
        if span.name != SPAN_LLM_GENERATE:
            continue
        if session_id and span.session_id != session_id:
            continue
        ctx = span.metrics.get("context")
        if not isinstance(ctx, dict):
            continue
        rows.append(
            {
                "session_id": span.session_id,
                "created_at": span.end_time.isoformat(),
                **ctx,
            }
        )
    rows.sort(key=lambda r: r["created_at"])
    return rows


def _format_context_show(summary: dict) -> str:
    last = summary["latest"]
    lines = [
        "ContextSnapshot summary:",
        f"  session_filter:           {summary['session_filter'] or '(all)'}",
        f"  model_calls_with_context: {summary['model_calls_with_context']}",
        f"  peak_conversation_tokens: {summary['peak_conversation_tokens']}",
        f"  peak_usage_ratio:         {summary['peak_usage_ratio'] * 100:.1f}%",
        "  latest:",
        f"    session_id:             {last['session_id']}",
        f"    at:                     {last['created_at']}",
        f"    conversation_tokens:    {last['conversation_tokens']}",
        f"    message_count:          {last['message_count']}",
        f"    limit_tokens:           {last['limit_tokens']}",
        f"    compaction_threshold:   {last['compaction_threshold_tokens']}",
        f"    usage_ratio:            {last['usage_ratio'] * 100:.1f}%",
        f"    threshold_ratio:        {last['threshold_ratio'] * 100:.1f}%",
    ]
    if "prompt_tokens_estimate" in last:
        lines.extend(
            [
                f"    prompt_tokens_estimate: {last['prompt_tokens_estimate']}",
                f"    static_block_tokens:    {last.get('static_block_tokens')}",
                f"    dynamic_block_tokens:   {last.get('dynamic_block_tokens')}",
            ]
        )
        names = last.get("prompt_block_names")
        if names:
            lines.append(f"    prompt_blocks:          {', '.join(names)}")
    breakdown = last.get("context_breakdown_tokens")
    if isinstance(breakdown, dict) and breakdown:
        lines.append("    context_breakdown_tokens:")
        for key in sorted(breakdown):
            lines.append(f"      - {key}: {breakdown[key]}")
    return "\n".join(lines)


def _format_context_series(rows: list[dict]) -> str:
    header = ("#", "at", "session", "conv_tok", "msgs", "usage%", "thr%")
    widths = [len(h) for h in header]
    table_rows: list[tuple[str, ...]] = []
    for i, row in enumerate(rows, 1):
        cells = (
            str(i),
            row["created_at"][:19],
            row["session_id"][:18],
            str(row["conversation_tokens"]),
            str(row["message_count"]),
            f"{row['usage_ratio'] * 100:.1f}",
            f"{row['threshold_ratio'] * 100:.1f}",
        )
        widths = [max(w, len(c)) for w, c in zip(widths, cells, strict=True)]
        table_rows.append(cells)
    fmt = "  ".join("{:<%d}" % w for w in widths)
    lines = [fmt.format(*header).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    for cells in table_rows:
        lines.append(fmt.format(*cells).rstrip())
    return "\n".join(lines)


if __name__ == "__main__":
    main()
