from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.contracts import MemoryStorePort, SessionStorePort
from harnesslab.core.loop import DEFAULT_MAX_STEPS, HarnessLoop
from harnesslab.core.models import Session
from harnesslab.core.prompt import (
    PromptBlock,
    build_agents_md_block,
    build_env_block,
    build_tool_guide_block,
)
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.eval.baseline import compare, load_baseline, save_baseline
from harnesslab.eval.loader import load_suite, load_task
from harnesslab.eval.report import render_stdout, write_json
from harnesslab.eval.runner import TaskRunner
from harnesslab.eval.task import TaskResult, TaskSuite
from harnesslab.improve import (
    dedupe_against_existing,
    generate,
    write_proposal,
)
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.memory.sqlite_store import SqliteMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.providers.deepseek import DeepSeekModel, tool_specs_from_registry
from harnesslab.replay import (
    UnreplayableTraceError,
    detect_divergence,
    group_by_session,
    read_trace,
    replay_session,
)
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.session.sqlite_store import SqliteSessionStore
from harnesslab.telemetry.aggregate import aggregate, render_metrics
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder
from harnesslab.tools.file_tools import (
    EditFileTool,
    GlobTool,
    GrepTool,
    ReadFileTool,
    WriteFileTool,
)
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.shell_tool import RunShellSafeTool

StorageBackend = Literal["memory", "sqlite"]
ModelBackend = Literal["simple", "deepseek"]

DEFAULT_SQLITE_PATH = ".harnesslab/state.sqlite"
DEFAULT_TASKS_DIR = "eval/tasks"
DEFAULT_BASELINE_PATH = "eval/baseline.json"
DEFAULT_REPORTS_DIR = "eval/reports"
DEFAULT_PROPOSALS_DIR = "proposals"
DEFAULT_MIN_OCCURRENCES = 2

SUBCOMMANDS = ("run", "eval", "replay", "metrics", "propose", "session")

EXIT_OK = 0
EXIT_UNREPLAYABLE = 2
EXIT_TASK_FAILED = 2
EXIT_REGRESSED = 3
EXIT_DIVERGED = 4
EXIT_USAGE = 64


def _make_dynamic_blocks_provider(
    workspace_root: Path,
    tools: ToolRegistry,
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


def build_runtime(
    workspace_root: Path,
    limits: RuntimeLimits | None = None,
    storage_backend: StorageBackend = "memory",
    sqlite_path: Path | None = None,
    model_backend: ModelBackend = "simple",
) -> HarnessLoop:
    limits = limits or RuntimeLimits()
    # Memory store is constructed for parity with the SessionStore but is
    # not yet consumed by the loop; the retrieval/writeback wiring is
    # deferred past Step 4.
    sessions, _ = _build_stores(storage_backend, workspace_root, sqlite_path)
    policy = DefaultPolicy(workspace_root=workspace_root)
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace_root, limits=limits))
    tools.register(WriteFileTool(workspace_root, limits=limits))
    tools.register(EditFileTool(workspace_root, limits=limits))
    tools.register(GrepTool(workspace_root, limits=limits))
    tools.register(GlobTool(workspace_root, limits=limits))
    tools.register(RunShellSafeTool(workspace_root, limits=limits))
    trace = JsonlTraceRecorder(workspace_root / ".harnesslab" / "trace.jsonl")
    if model_backend == "deepseek":
        model = DeepSeekModel(
            tool_specs_provider=lambda: tool_specs_from_registry(tools.list()),
            dynamic_blocks_provider=_make_dynamic_blocks_provider(
                workspace_root, tools
            ),
        )
    else:
        model = SimpleModel()
    return HarnessLoop(
        model=model,
        policy=policy,
        sessions=sessions,
        tools=tools,
        trace=trace,
        clock=SystemClock(),
        ids=UuidIdProvider(),
        limits=limits,
    )


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harnesslab",
        description="HarnessLab CLI — run a single turn or the eval suite.",
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
        default="simple",
        choices=["simple", "deepseek"],
        help=(
            "Model backend for `run` (default: simple). "
            "Use `deepseek` to call DeepSeek with DEEPSEEK_API_KEY."
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

    rs = se_sub.add_parser("resume", help="Run another turn on an existing session.")
    rs.add_argument("session_id")
    rs.add_argument("input", help="The next user message for this session.")
    rs.add_argument(
        "--model",
        default="simple",
        choices=["simple", "deepseek"],
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
    if args.command == "session":
        sys.exit(_cmd_session(args))

    parser.print_help(sys.stderr)
    sys.exit(EXIT_USAGE)


# ---------------------------------------------------------------------------
# subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    if args.max_steps < 1:
        print(
            f"--max-steps must be >= 1, got {args.max_steps}",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        loop = build_runtime(
            workspace_root=workspace_root,
            storage_backend=args.storage,
            sqlite_path=sqlite_path,
            model_backend=args.model,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    session = loop.start(goal=args.input)
    response = loop.run_session(session.id, args.input, max_steps=args.max_steps)
    print(response)
    return EXIT_OK


def _cmd_eval(args: argparse.Namespace) -> int:
    tasks_dir = Path(args.tasks_dir)
    baseline_path = Path(args.baseline)
    reports_dir = Path(args.reports_dir)

    suite = _load_suite_or_single(tasks_dir, args.task)
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
    trace_path = Path(args.trace)
    if not trace_path.exists():
        raise SystemExit(f"trace file not found: {trace_path}")
    try:
        events = read_trace(trace_path)
    except json.JSONDecodeError as exc:
        print(f"invalid JSONL trace: {exc}", file=sys.stderr)
        return EXIT_UNREPLAYABLE

    grouped = group_by_session(events)
    if args.session_id is not None:
        if args.session_id not in grouped:
            print(
                f"session id {args.session_id!r} not found in trace "
                f"(present: {list(grouped.keys())})",
                file=sys.stderr,
            )
            return EXIT_UNREPLAYABLE
        grouped = {args.session_id: grouped[args.session_id]}

    workspace_root = Path(args.workspace).resolve() if args.workspace else None

    any_divergence = False
    for sid, session_events in grouped.items():
        try:
            replayed = replay_session(session_events, workspace_root=workspace_root)
        except UnreplayableTraceError as exc:
            print(f"[{sid}] unreplayable: {exc}", file=sys.stderr)
            return EXIT_UNREPLAYABLE
        report = detect_divergence(session_events, replayed, strict=args.strict)
        print(f"[{sid}] {report.render()}")
        if not report.matched:
            any_divergence = True

    return EXIT_DIVERGED if any_divergence else EXIT_OK


def _cmd_metrics(args: argparse.Namespace) -> int:
    trace_path = Path(args.trace)
    if not trace_path.exists():
        raise SystemExit(f"trace file not found: {trace_path}")
    try:
        events = read_trace(trace_path)
    except json.JSONDecodeError as exc:
        print(f"invalid JSONL trace: {exc}", file=sys.stderr)
        return EXIT_USAGE

    metrics = aggregate(events)
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

    events = []
    if args.trace:
        trace_path = Path(args.trace)
        if not trace_path.exists():
            raise SystemExit(f"trace file not found: {trace_path}")
        try:
            events = read_trace(trace_path)
        except json.JSONDecodeError as exc:
            print(f"invalid JSONL trace: {exc}", file=sys.stderr)
            return EXIT_USAGE

    eval_results: list[TaskResult] | None = None
    if args.eval_report:
        report_path = Path(args.eval_report)
        if not report_path.exists():
            raise SystemExit(f"eval report not found: {report_path}")
        eval_results = _load_eval_results(report_path)

    out_dir = Path(args.out)
    proposals = generate(
        events,
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


def _format_session_table(sessions) -> str:
    header = ("ID", "STATUS", "STEPS", "TURNS", "CREATED", "TITLE")
    rows = [header]
    for s in sessions:
        rows.append(
            (
                s.id,
                s.status,
                str(s.step_count),
                str(s.turn_count),
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
    ]
    if include_messages:
        lines.append("")
        lines.append(f"Messages ({len(session.messages)}):")
        for i, msg in enumerate(session.messages):
            preview = msg.content if len(msg.content) <= 120 else msg.content[:117] + "..."
            lines.append(f"  [{i}] {msg.role}: {preview}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
