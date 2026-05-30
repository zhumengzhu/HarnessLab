"""Tests for `harnesslab replay` and `harnesslab metrics` subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesslab import cli
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.replay import ReplayModel, ReplaySpanRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.eval.loader import load_suite
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.replay import read_spans
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.local_span_recorder import LocalSpanRecorder
from harnesslab.tools.file_tools import ReadFileTool, WriteFileTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.shell_tool import RunShellSafeTool
from harnesslab.tools.spawn_sub_agent import SpawnSubAgentTool

TASKS_DIR = Path(__file__).resolve().parents[1] / "eval" / "tasks"


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _write_real_trace(workspace: Path, trace_path: Path, task_name: str) -> None:
    """Drive a real eval task end-to-end, persisting its trace as JSONL."""
    suite = load_suite(TASKS_DIR)
    task = next(t for t in suite.tasks if t.name == task_name)

    limits = RuntimeLimits()
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace, limits=limits))
    tools.register(WriteFileTool(workspace, limits=limits))
    tools.register(RunShellSafeTool(workspace, limits=limits))
    model = ReplayModel(decisions=task.decisions) if task.decisions else SimpleModel()
    recorder = LocalSpanRecorder(trace_path)
    in_memory = ReplaySpanRecorder()  # noqa: F841 - kept for symmetry

    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(workspace_root=workspace),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
    )
    session = loop.start(goal=task.goal)
    for turn in task.turns:
        loop.run_turn(session.id, turn.input)


def _write_spawn_trace(workspace: Path, trace_path: Path) -> str:
    """Run spawn_sub_agent once; return parent session id."""

    tools = ToolRegistry()
    loop_holder: list[HarnessLoop] = []
    recorder = LocalSpanRecorder(trace_path)
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(workspace, enable_spawn_sub_agent=True),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
        workspace_root=workspace,
    )
    loop_holder.append(loop)
    tools.register(SpawnSubAgentTool(lambda: loop_holder[0]))
    parent = loop.start(goal="supervisor")
    loop.run_session(
        parent.id,
        '/tool spawn_sub_agent {"goal": "/final child done", "max_steps": 1}',
        max_steps=1,
    )
    return parent.id


# ---------- harnesslab replay ----------


def test_replay_matches_real_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    trace = tmp_path / "trace.jsonl"
    _write_real_trace(workspace, trace, "write_then_read")

    monkeypatch.setattr("sys.argv", ["harnesslab", "replay", str(trace)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK, out
    assert "OK: replay matches original" in out


def test_replay_diverges_when_trace_tampered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    trace = tmp_path / "trace.jsonl"
    _write_real_trace(workspace, trace, "write_then_read")

    lines = trace.read_text(encoding="utf-8").splitlines()
    tampered_lines: list[str] = []
    flipped = False
    for line in lines:
        obj = json.loads(line)
        if not flipped and obj.get("name") == "harnesslab.step":
            for event in obj.get("events", []):
                if (
                    event.get("name") == "decision.applied"
                    and event.get("attributes", {}).get("tool_name") == "write_file"
                ):
                    event["attributes"]["tool_name"] = "read_file"
                    flipped = True
                    break
        tampered_lines.append(json.dumps(obj))
    assert flipped
    trace.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["harnesslab", "replay", str(trace)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_DIVERGED, out
    assert "DIVERGED" in out


def test_replay_unreplayable_trace_returns_exit_2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        json.dumps(
            {
                "trace_id": "t" * 32,
                "span_id": "s" * 16,
                "name": "harnesslab.turn",
                "session_id": "r",
                "turn_index": 0,
                "start_time": "2026-01-01T00:00:00+00:00",
                "end_time": "2026-01-01T00:00:01+00:00",
                "duration_ms": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("sys.argv", ["harnesslab", "replay", str(trace)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == cli.EXIT_UNREPLAYABLE
    assert "unreplayable" in err


def test_replay_unknown_session_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    trace = tmp_path / "trace.jsonl"
    _write_real_trace(workspace, trace, "assistant_fallback")

    monkeypatch.setattr(
        "sys.argv",
        ["harnesslab", "replay", str(trace), "--session-id", "ses_nope"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == cli.EXIT_UNREPLAYABLE
    assert "not found" in err


def test_replay_missing_trace_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["harnesslab", "replay", str(tmp_path / "missing.jsonl")]
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "spans file not found" in str(exc.value)


def test_replay_with_shared_workspace_round_trips_across_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When a write_file session is followed by a read_file session that
    depends on the written file, default tmp-workspace replay diverges
    on the read. Passing the original workspace via --workspace makes
    the round-trip succeed."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    trace = tmp_path / "trace.jsonl"

    # Two sessions sharing the same workspace, second depends on first.
    limits = RuntimeLimits()
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace, limits=limits))
    tools.register(WriteFileTool(workspace, limits=limits))
    tools.register(RunShellSafeTool(workspace, limits=limits))
    recorder = LocalSpanRecorder(trace)
    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(workspace_root=workspace),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=recorder,
        clock=FrozenClock(start=DEFAULT_REPLAY_CLOCK_START),
        ids=SeqIdProvider(),
    )
    s1 = loop.start(goal="write")
    loop.run_turn(s1.id, '/tool write_file {"path":"shared.txt","content":"hi"}')
    s2 = loop.start(goal="read")
    loop.run_turn(s2.id, '/tool read_file {"path":"shared.txt"}')

    monkeypatch.setattr(
        "sys.argv", ["harnesslab", "replay", str(trace), "--workspace", str(workspace)]
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK, out
    assert out.count("OK: replay matches original") == 2


def test_replay_include_children_replays_parent_and_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    trace = tmp_path / "spawn.jsonl"
    parent_id = _write_spawn_trace(workspace, trace)
    spans = read_spans(trace)
    session_ids = {s.session_id for s in spans if s.name == "harnesslab.turn"}
    assert len(session_ids) >= 2

    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "replay",
            str(trace),
            "--session-id",
            parent_id,
            "--include-children",
            "--workspace",
            str(workspace),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK, out
    assert out.count("OK: replay matches original") == 2


# ---------- harnesslab metrics ----------


def test_metrics_human_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    trace = tmp_path / "trace.jsonl"
    _write_real_trace(workspace, trace, "write_then_read")

    monkeypatch.setattr("sys.argv", ["harnesslab", "metrics", str(trace)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK
    assert "Metrics:" in out
    assert "sessions:        1" in out
    assert "tool_calls:      2" in out
    assert "tool_success:    100.0%" in out


def test_metrics_json_output_is_parseable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    trace = tmp_path / "trace.jsonl"
    _write_real_trace(workspace, trace, "assistant_fallback")

    monkeypatch.setattr("sys.argv", ["harnesslab", "metrics", str(trace), "--json"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == cli.EXIT_OK
    parsed = json.loads(out)
    assert parsed["sessions"] == 1
    assert parsed["tool_calls"] == 0
    assert parsed["tool_success_rate"] is None


def test_metrics_missing_trace_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["harnesslab", "metrics", str(tmp_path / "missing.jsonl")]
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "spans file not found" in str(exc.value)
