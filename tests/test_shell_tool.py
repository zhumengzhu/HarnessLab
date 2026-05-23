from pathlib import Path

from harnesslab.cli import build_runtime


def test_shell_tool_allows_allowlisted_command(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="shell")
    reply = loop.run_turn(session.id, '/tool run_shell_safe {"command":"pwd"}')
    assert "[tool:run_shell_safe]" in reply


def test_shell_tool_blocks_non_allowlisted_command(tmp_path: Path) -> None:
    loop = build_runtime(tmp_path)
    session = loop.start(goal="shell deny")
    reply = loop.run_turn(
        session.id,
        '/tool run_shell_safe {"command":"python3 -c \\"print(1)\\""}',
    )
    assert "Tool denied by policy" in reply

