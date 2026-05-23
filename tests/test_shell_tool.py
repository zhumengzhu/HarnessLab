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
        '/tool run_shell_safe {"command":"arbitrary-binary --do-stuff"}',
    )
    assert "Tool denied by policy" in reply


def test_shell_tool_blocks_destructive_git_subcommand(tmp_path: Path) -> None:
    """``git`` is on the allowlist, but write-side subcommands stay blocked."""

    loop = build_runtime(tmp_path)
    session = loop.start(goal="shell git deny")
    reply = loop.run_turn(
        session.id,
        '/tool run_shell_safe {"command":"git push origin main"}',
    )
    assert "Tool denied by policy" in reply
    assert "git subcommand" in reply

