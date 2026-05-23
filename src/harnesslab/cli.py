from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.contracts import MemoryStorePort, SessionStorePort
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.eval.baseline import compare, load_baseline, save_baseline
from harnesslab.eval.loader import load_suite, load_task
from harnesslab.eval.report import render_stdout, write_json
from harnesslab.eval.runner import TaskRunner
from harnesslab.eval.task import TaskSuite
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.memory.sqlite_store import SqliteMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.session.sqlite_store import SqliteSessionStore
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.shell_tool import RunShellSafeTool

StorageBackend = Literal["memory", "sqlite"]

DEFAULT_SQLITE_PATH = ".harnesslab/state.sqlite"
DEFAULT_TASKS_DIR = "eval/tasks"
DEFAULT_BASELINE_PATH = "eval/baseline.json"
DEFAULT_REPORTS_DIR = "eval/reports"

SUBCOMMANDS = ("run", "eval")

EXIT_OK = 0
EXIT_TASK_FAILED = 2
EXIT_REGRESSED = 3
EXIT_USAGE = 64


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
    tools.register(RunShellSafeTool(workspace_root, limits=limits))
    trace = JsonlTraceRecorder(workspace_root / ".harnesslab" / "trace.jsonl")
    model = SimpleModel()
    return HarnessLoop(
        model=model,
        policy=policy,
        sessions=sessions,
        tools=tools,
        trace=trace,
        clock=SystemClock(),
        ids=UuidIdProvider(),
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

    parser.print_help(sys.stderr)
    sys.exit(EXIT_USAGE)


# ---------------------------------------------------------------------------
# subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else None
    loop = build_runtime(
        workspace_root=workspace_root,
        storage_backend=args.storage,
        sqlite_path=sqlite_path,
    )
    session = loop.start(goal=args.input)
    response = loop.run_turn(session.id, args.input)
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


if __name__ == "__main__":
    main()
