from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.contracts import MemoryStorePort, SessionStorePort
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
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
    # not yet consumed by the loop; the retrieval/writeback wiring lands
    # with the Step 4 eval work.
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


def main() -> None:
    parser = argparse.ArgumentParser(description="HarnessLab CLI")
    parser.add_argument("input", help="User input or tool command")
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used by file and shell tools",
    )
    parser.add_argument(
        "--storage",
        default="memory",
        choices=["memory", "sqlite"],
        help="Backend for session and memory stores (default: memory).",
    )
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help=(
            "SQLite DB path. Relative paths resolve against --workspace-root. "
            f"Defaults to {DEFAULT_SQLITE_PATH!r} when --storage=sqlite."
        ),
    )
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
