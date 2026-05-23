from __future__ import annotations

import argparse
from pathlib import Path

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.jsonl_recorder import JsonlTraceRecorder
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.shell_tool import RunShellSafeTool


def build_runtime(workspace_root: Path) -> HarnessLoop:
    sessions = InMemorySessionStore()
    policy = DefaultPolicy(workspace_root=workspace_root)
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace_root))
    tools.register(WriteFileTool(workspace_root))
    tools.register(RunShellSafeTool(workspace_root))
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
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    loop = build_runtime(workspace_root)
    session = loop.start(goal=args.input)
    response = loop.run_turn(session.id, args.input)
    print(response)


if __name__ == "__main__":
    main()
