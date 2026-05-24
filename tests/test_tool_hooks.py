"""Unit tests for tool lifecycle hook runner."""

from __future__ import annotations

from harnesslab.core.models import ToolCall, ToolResult
from harnesslab.core.tool_hooks import build_hook_runner


def test_prompt_pre_hook_can_block_matching_tool() -> None:
    runner = build_hook_runner(
        (
            {
                "name": "block-shell",
                "type": "prompt",
                "config": {
                    "tool_name_contains": "run_shell_safe",
                    "action": "block",
                    "reason": "blocked",
                },
            },
        ),
        (),
    )
    call = ToolCall(name="run_shell_safe", args={"command": "pwd"}, session_id="ses_1")
    decision = runner.run_pre(runner.pre_hooks[0], call)
    assert decision.action == "block"
    assert decision.reason == "blocked"


def test_prompt_post_hook_is_allow_when_not_matching() -> None:
    runner = build_hook_runner(
        (),
        (
            {
                "name": "post-audit",
                "type": "prompt",
                "config": {
                    "tool_name_contains": "write_file",
                    "action": "warn",
                },
            },
        ),
    )
    call = ToolCall(name="read_file", args={"path": "a.txt"}, session_id="ses_1")
    result = ToolResult(ok=True, output="x")
    decision = runner.run_post(runner.post_hooks[0], call, result)
    assert decision.action == "allow"
