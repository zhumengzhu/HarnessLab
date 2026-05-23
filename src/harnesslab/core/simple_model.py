from __future__ import annotations

import json

from harnesslab.core.models import Decision, Session


class SimpleModel:
    """
    A deterministic teaching model.

    Supported command shape:
    /tool <tool_name> <json_args>
    """

    def decide(self, session: Session, user_input: str) -> Decision:
        text = user_input.strip()
        if text.startswith("/tool "):
            parts = text.split(" ", maxsplit=2)
            if len(parts) < 3:
                return Decision(
                    kind="assistant",
                    assistant_message="Use: /tool <name> <json_args>",
                )
            tool_name = parts[1]
            try:
                tool_args = json.loads(parts[2])
            except json.JSONDecodeError:
                return Decision(
                    kind="assistant",
                    assistant_message="Invalid JSON args for tool call.",
                )
            return Decision(kind="tool", tool_name=tool_name, tool_args=tool_args)

        return Decision(
            kind="assistant",
            assistant_message=(
                "HarnessLab is ready. Use '/tool <name> <json_args>' to call tools."
            ),
        )

