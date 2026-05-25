"""Minimal MCP stdio JSON-RPC client (lazy import; no SDK required)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class McpToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class McpServerClient:
    """Talk to one MCP server over stdio."""

    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    _proc: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)
    last_error: str | None = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        if self._proc is not None:
            return
        env = {**os.environ, **self.env}
        self._proc = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "harnesslab", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
        self._initialized = True

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        self._initialized = False
        if proc is None:
            return
        try:
            proc.terminate()
        except OSError:
            pass

    def list_tools(self) -> list[McpToolSpec]:
        self.connect()
        result = self._request("tools/list", {})
        tools_raw = result.get("tools", []) if isinstance(result, dict) else []
        out: list[McpToolSpec] = []
        for item in tools_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            schema = item.get("inputSchema")
            input_schema = schema if isinstance(schema, dict) else {"type": "object"}
            out.append(
                McpToolSpec(
                    name=name,
                    description=str(item.get("description", "")),
                    input_schema=input_schema,
                )
            )
        return out

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        self.connect()
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict):
            return str(result)
        content = result.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            return "\n".join(parts).strip() or json.dumps(result)
        if result.get("isError"):
            return json.dumps(result)
        return json.dumps(result)

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        with self._lock:
            self._request_id += 1
            req_id = self._request_id
            payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            proc = self._proc
            if proc is None or proc.stdin is None or proc.stdout is None:
                raise RuntimeError("MCP process not running")
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            while True:
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError("MCP server closed stdout")
                data = json.loads(line)
                if data.get("id") == req_id:
                    if "error" in data:
                        err = data["error"]
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        self.last_error = msg
                        raise RuntimeError(msg)
                    return data.get("result")

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("MCP process not running")
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()
