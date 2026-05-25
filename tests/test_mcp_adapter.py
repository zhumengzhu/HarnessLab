"""Tests for MCP adapter (Phase 5.4)."""

from __future__ import annotations

import sys
from pathlib import Path

from harnesslab.core.models import ToolCall
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.tools.mcp_adapter import McpServerConfig, mcp_tool_name, register_mcp_servers
from harnesslab.tools.registry import ToolRegistry

ECHO_SERVER = Path(__file__).resolve().parent / "fixtures" / "mcp_echo_server.py"


def test_mcp_echo_round_trip(tmp_path: Path) -> None:
    registry = ToolRegistry()
    health = register_mcp_servers(
        registry,
        (
            McpServerConfig(
                name="echo",
                command=sys.executable,
                args=(str(ECHO_SERVER),),
                allowed_tools=frozenset({mcp_tool_name("echo", "echo")}),
            ),
        ),
    )
    assert health["echo"]["status"] == "ok"
    tool_name = mcp_tool_name("echo", "echo")
    policy = DefaultPolicy(tmp_path, mcp_allowed_tools=frozenset({tool_name}))
    call = ToolCall(name=tool_name, args={"message": "hello-mcp"})
    allowed, _ = policy.allow_tool(call)
    assert allowed
    result = registry.execute(call)
    assert result.ok is True
    assert result.output == "hello-mcp"
