from pathlib import Path

from harnesslab.cli import build_runtime
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

