from __future__ import annotations

import json

from harnesslab.core.models import Decision, Session


class SimpleModel:
    """
    A deterministic teaching model.

    Supported command shapes:

    - ``/tool <tool_name> <json_args>`` → ``kind="tool"`` (non-terminal;
      the loop will execute the tool and call this model again)
    - ``/plan <message>`` → ``kind="plan"`` (non-terminal planning step)
    - ``/final <message>`` → ``kind="final"`` (terminal answer)
    - ``/ask <message>`` → ``kind="ask_user"`` (terminal pause)
    - anything else → ``kind="final"`` with the canned greeting

    Empty input is used by ``HarnessLoop.run_session`` on follow-up steps
    after a tool call; the model answers with the canned final message so
    the loop terminates cleanly. Real model adapters use ``session.messages``
    for that signal.
    """

    _CANNED_FINAL = (
        "HarnessLab is ready. Use '/tool <name> <json_args>' to call tools, "
        "'/final <msg>' to end the session, or '/ask <msg>' to pause for input."
    )

    def decide(self, session: Session, user_input: str) -> Decision:
        text = user_input.strip()

        if text.startswith("/tool "):
            parts = text.split(" ", maxsplit=2)
            if len(parts) < 3:
                return Decision(
                    kind="final",
                    assistant_message="Use: /tool <name> <json_args>",
                )
            tool_name = parts[1]
            try:
                tool_args = json.loads(parts[2])
            except json.JSONDecodeError:
                return Decision(
                    kind="final",
                    assistant_message="Invalid JSON args for tool call.",
                )
            return Decision(kind="tool", tool_name=tool_name, tool_args=tool_args)

        if text.startswith("/final "):
            return Decision(
                kind="final",
                assistant_message=text[len("/final ") :].strip() or self._CANNED_FINAL,
            )

        if text.startswith("/plan "):
            return Decision(
                kind="plan",
                assistant_message=text[len("/plan ") :].strip() or "Plan drafted.",
            )

        if text.startswith("/ask "):
            return Decision(
                kind="ask_user",
                assistant_message=text[len("/ask ") :].strip() or "Awaiting input.",
            )

        return Decision(kind="final", assistant_message=self._CANNED_FINAL)

