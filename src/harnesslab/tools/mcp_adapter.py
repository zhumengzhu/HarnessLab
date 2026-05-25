"""Map MCP server tools into ToolPort instances (Phase 5.4)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from harnesslab.core.models import ToolCall, ToolResult
from harnesslab.tools.mcp_client import McpServerClient, McpToolSpec
from harnesslab.tools.registry import ToolRegistry

_SAFE = re.compile(r"[^a-z0-9_]+")


def mcp_tool_name(server_name: str, tool_name: str) -> str:
    server = _SAFE.sub("_", server_name.strip().lower()).strip("_")
    tool = _SAFE.sub("_", tool_name.strip().lower()).strip("_")
    return f"mcp_{server}_{tool}"


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env_names: tuple[str, ...] = ()
    policy_profile: str = "strict"
    allowed_tools: frozenset[str] = frozenset()


class McpToolAdapter:
    """One MCP tool exposed as a native ToolPort."""

    def __init__(
        self,
        *,
        server: McpServerClient,
        spec: McpToolSpec,
        prefixed_name: str,
    ) -> None:
        self._server = server
        self._spec = spec
        self.name = prefixed_name
        self.description = spec.description or f"MCP tool {spec.name}"
        self.args_schema = spec.input_schema

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            output = self._server.call_tool(self._spec.name, dict(call.args))
            return ToolResult(ok=True, output=output)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, output="", error=str(exc))


def register_mcp_servers(
    registry: ToolRegistry,
    configs: tuple[McpServerConfig, ...],
) -> dict[str, dict[str, Any]]:
    """Connect MCP servers and register prefixed tools. Returns health map."""

    health: dict[str, dict[str, Any]] = {}
    for cfg in configs:
        env = {name: val for name in cfg.env_names if (val := os.environ.get(name))}
        client = McpServerClient(command=cfg.command, args=cfg.args, env=env)
        try:
            tools = client.list_tools()
            registered = 0
            for spec in tools:
                prefixed = mcp_tool_name(cfg.name, spec.name)
                if (
                    cfg.allowed_tools
                    and prefixed not in cfg.allowed_tools
                    and spec.name not in cfg.allowed_tools
                ):
                    continue
                registry.register(
                    McpToolAdapter(server=client, spec=spec, prefixed_name=prefixed)
                )
                registered += 1
            health[cfg.name] = {"status": "ok", "tools": registered, "error": None}
        except Exception as exc:  # noqa: BLE001
            health[cfg.name] = {"status": "error", "tools": 0, "error": str(exc)}
            client.close()
    return health
