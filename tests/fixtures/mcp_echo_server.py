#!/usr/bin/env python3
"""Minimal stdio MCP echo server for contract tests."""

from __future__ import annotations

import json
import sys


def main() -> None:
    while True:
        line = sys.stdin.readline()
        if not line:
            return
        req = json.loads(line)
        method = req.get("method")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            _respond(
                req,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "echo", "version": "1"},
                },
            )
        elif method == "tools/list":
            _respond(
                req,
                {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echo a message",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"message": {"type": "string"}},
                                "required": ["message"],
                            },
                        }
                    ]
                },
            )
        elif method == "tools/call":
            args = req.get("params", {}).get("arguments", {})
            message = str(args.get("message", ""))
            _respond(
                req,
                {"content": [{"type": "text", "text": message}]},
            )


def _respond(req: dict, result: dict) -> None:
    sys.stdout.write(
        json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": result}) + "\n"
    )
    sys.stdout.flush()


if __name__ == "__main__":
    main()
