from pathlib import Path

from harnesslab.cli import build_runtime
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.operator_config import OperatorConfig


def test_assistant_fallback_message(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="hello")
    reply = loop.run_turn(session.id, "hello")
    assert "HarnessLab is ready" in reply


def test_tool_write_then_read(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="write file")

    write_cmd = '/tool write_file {"path":"notes/a.txt","content":"hi"}'
    write_reply = loop.run_turn(session.id, write_cmd)
    assert "[tool:write_file]" in write_reply

    read_cmd = '/tool read_file {"path":"notes/a.txt"}'
    read_reply = loop.run_turn(session.id, read_cmd)
    assert "[tool:read_file] hi" in read_reply


def test_policy_denies_outside_workspace(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="bad path")
    reply = loop.run_turn(
        session.id,
        '/tool read_file {"path":"../../etc/passwd"}',
    )
    assert "Tool denied by policy" in reply


def test_skill_command_lists_and_selects_session_skills(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("search deeply", encoding="utf-8")
    (skills / "debug.md").write_text("repro first", encoding="utf-8")

    loop = build_runtime(tmp_path)
    session = loop.start(goal="skills")

    listed = loop.run_turn(session.id, "/skill list")
    assert "Skills available:" in listed
    assert "- research" in listed
    assert "- debug" in listed
    assert "Selected skills: (none)" in listed

    added = loop.run_turn(session.id, "/skill add research")
    assert "Selected skill 'research'" in added

    listed_again = loop.run_turn(session.id, "/skill")
    assert "Selected skills: research" in listed_again


def test_direct_skill_slash_pins_skill(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("search deeply", encoding="utf-8")

    loop = build_runtime(tmp_path)
    session = loop.start(goal="slash skill")
    reply = loop.run_turn(session.id, "/research")
    assert "Selected skill 'research'" in reply


def test_direct_skill_slash_with_task_runs_model(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("search deeply", encoding="utf-8")

    loop = build_runtime(tmp_path)
    session = loop.start(goal="slash skill")
    reply = loop.run_turn(session.id, "/research investigate topic X")
    assert "Selected skill" not in reply
    assert "HarnessLab is ready" in reply

    listed = loop.run_turn(session.id, "/skill list")
    assert "Selected skills: research" in listed


def test_stream_reasoning_persisted_on_tool_turn(tmp_path: Path) -> None:
    from harnesslab.core.models import Decision
    from harnesslab.core.runtime import SystemClock, UuidIdProvider
    from harnesslab.core.stream_context import emit_stream_delta, stream_sink_active
    from harnesslab.policy.default_policy import DefaultPolicy
    from harnesslab.session.in_memory import InMemorySessionStore
    from harnesslab.telemetry.local_span_recorder import LocalSpanRecorder
    from harnesslab.tools.registry import ToolRegistry

    class StreamReasoningModel:
        def decide(self, session, user_input: str) -> Decision:
            if stream_sink_active():
                emit_stream_delta("reasoning", "plan: search web")
            return Decision(
                kind="tool",
                tool_name="grep",
                tool_args={"pattern": "x"},
            )

        def last_call_meta(self) -> dict:
            return {}

    from harnesslab.tools.file_tools import GrepTool

    tools = ToolRegistry()
    tools.register(GrepTool(tmp_path))
    loop = HarnessLoop(
        model=StreamReasoningModel(),
        policy=DefaultPolicy(tmp_path),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=LocalSpanRecorder(tmp_path / "trace.jsonl"),
        clock=SystemClock(),
        ids=UuidIdProvider(),
        workspace_root=tmp_path,
        stream_sink=lambda *_args: None,
    )
    session = loop.start(goal="stream reasoning")
    loop.run_turn(session.id, "search")
    assistant = [m for m in session.messages if m.role == "assistant" and m.tool_calls]
    assert assistant
    assert assistant[-1].reasoning_text == "plan: search web"


def test_max_steps_appends_continue_hint(tmp_path: Path) -> None:
    from harnesslab.core.models import Decision
    from harnesslab.core.runtime import SystemClock, UuidIdProvider
    from harnesslab.policy.default_policy import DefaultPolicy
    from harnesslab.session.in_memory import InMemorySessionStore
    from harnesslab.telemetry.local_span_recorder import LocalSpanRecorder
    from harnesslab.tools.file_tools import GrepTool
    from harnesslab.tools.registry import ToolRegistry

    class AlwaysToolModel:
        def decide(self, session, user_input: str) -> Decision:
            return Decision(kind="tool", tool_name="grep", tool_args={"pattern": "x"})

        def last_call_meta(self) -> dict:
            return {}

    tools = ToolRegistry()
    tools.register(GrepTool(tmp_path))
    loop = HarnessLoop(
        model=AlwaysToolModel(),
        policy=DefaultPolicy(tmp_path),
        sessions=InMemorySessionStore(),
        tools=tools,
        spans=LocalSpanRecorder(tmp_path / "trace.jsonl"),
        clock=SystemClock(),
        ids=UuidIdProvider(),
        workspace_root=tmp_path,
    )
    session = loop.start(goal="research")
    reply = loop.run_session(session.id, "keep searching", max_steps=2)
    assert "Step budget reached" in reply
    assert session.status == "waiting_user"
    assert any(
        "Step budget reached" in m.content for m in session.messages if m.role == "assistant"
    )


def test_compact_command_runs_manual_compaction(tmp_path: Path) -> None:
    from harnesslab.core.config import RuntimeLimits
    from harnesslab.core.replay import ReplaySpanRecorder

    recorder = ReplaySpanRecorder()
    loop = build_runtime(
        tmp_path,
        limits=RuntimeLimits(compaction_keep_last_messages=2),
        spans=recorder,
    )
    session = loop.start(goal="long chat")
    for i in range(6):
        session.messages.append(
            loop._make_message(  # noqa: SLF001
                role="user" if i % 2 == 0 else "assistant",
                content=f"msg-{i}-{'x' * 80}",
                session=session,
            )
        )
    loop._sessions.save(session)  # noqa: SLF001

    reply = loop.run_turn(session.id, "/compact")
    assert "Compacted session context" in reply

    refreshed = loop._sessions.get(session.id)  # noqa: SLF001
    assert any(m.role == "system" and "Compacted" in m.content for m in refreshed.messages)
    from span_assertions import compact_spans

    compacts = compact_spans(recorder.spans)
    assert compacts
    assert compacts[-1].attributes.get("harnesslab.compaction.trigger") == "manual"


def test_skill_command_clear_removes_selected_skills(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "research.md").write_text("search deeply", encoding="utf-8")
    loop = build_runtime(tmp_path)
    session = loop.start(goal="skills clear")
    loop.run_turn(session.id, "/skill add research")
    cleared = loop.run_turn(session.id, "/skill clear")
    assert "Cleared selected skills" in cleared
    listed = loop.run_turn(session.id, "/skill")
    assert "Selected skills: (none)" in listed


def test_pre_tool_hook_can_block_run_shell_safe(tmp_path: Path) -> None:
    loop = build_runtime(
        tmp_path,
        operator_config=OperatorConfig(
            pre_tool_hooks=(
                {
                    "name": "pre-block-shell",
                    "type": "prompt",
                    "config": {
                        "tool_name_contains": "run_shell_safe",
                        "action": "block",
                        "reason": "shell blocked by policy hook",
                    },
                },
            )
        ),
    )
    session = loop.start(goal="hook block")
    reply = loop.run_turn(
        session.id,
        '/tool run_shell_safe {"command":"pwd"}',
    )
    assert "Tool denied by hook" in reply
    assert "shell blocked by policy hook" in reply

