from pathlib import Path

from harnesslab.cli import build_runtime


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

