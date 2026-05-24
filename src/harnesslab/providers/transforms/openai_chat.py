"""OpenAI Chat Completions transform (DeepSeek, many proxies)."""

from __future__ import annotations

import json
from typing import Any

from harnesslab.core.models import Decision, Session
from harnesslab.core.prompt import ComposedPrompt
from harnesslab.providers.catalog import CatalogEntry
from harnesslab.providers.transforms.types import ParsedModelTurn, ReplayPolicy


def replay_policy(session: Session, entry: CatalogEntry) -> ReplayPolicy:
    """Decide whether assistant reasoning must be replayed on the wire."""

    if entry.reasoning_support == "none":
        return ReplayPolicy(
            include_reasoning_in_tool_loop=False,
            drop_reasoning_on_new_user_turn=True,
        )
    in_tool_loop = bool(session.messages and session.messages[-1].role == "tool")
    return ReplayPolicy(
        include_reasoning_in_tool_loop=in_tool_loop,
        drop_reasoning_on_new_user_turn=True,
    )


def serialize_messages(
    composed: ComposedPrompt,
    session: Session,
    entry: CatalogEntry,
) -> list[dict[str, Any]]:
    """Build OpenAI-style messages, applying replay policy for reasoning."""

    wire = composed.as_openai_messages()
    policy = replay_policy(session, entry)
    if not policy.include_reasoning_in_tool_loop:
        return wire
    assistant_id = _open_tool_loop_assistant_id(session)
    if assistant_id is None:
        return wire
    reasoning = _reasoning_for_message(session, assistant_id)
    if not reasoning:
        return wire
    return _inject_reasoning_on_assistant(wire, reasoning)


def parse_response(
    payload: dict[str, Any],
    entry: CatalogEntry | None = None,
) -> ParsedModelTurn:
    """Translate one chat-completions response into a normalized turn."""

    _ = entry  # reserved for per-model parse quirks in later phases
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="DeepSeek response invalid: missing choices.",
            )
        )
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message", {})
    if not isinstance(message, dict):
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="DeepSeek response invalid: malformed message.",
            )
        )

    reasoning_raw = message.get("reasoning_content")
    reasoning_text = (
        reasoning_raw.strip()
        if isinstance(reasoning_raw, str) and reasoning_raw.strip()
        else None
    )

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        function = tool_calls[0].get("function", {}) if isinstance(tool_calls[0], dict) else {}
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not name:
            return ParsedModelTurn(
                decision=Decision(
                    kind="final",
                    assistant_message="DeepSeek tool call invalid: missing function name.",
                ),
                reasoning_text=reasoning_text,
            )
        if not isinstance(arguments, str):
            return ParsedModelTurn(
                decision=Decision(
                    kind="final",
                    assistant_message=(
                        "DeepSeek tool call invalid: arguments must be a JSON string."
                    ),
                ),
                reasoning_text=reasoning_text,
            )
        try:
            tool_args = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return ParsedModelTurn(
                decision=Decision(
                    kind="final",
                    assistant_message=f"DeepSeek tool call invalid JSON args: {exc.msg}",
                ),
                reasoning_text=reasoning_text,
            )
        if not isinstance(tool_args, dict):
            return ParsedModelTurn(
                decision=Decision(
                    kind="final",
                    assistant_message="DeepSeek tool call invalid: JSON args must be an object.",
                ),
                reasoning_text=reasoning_text,
            )
        return ParsedModelTurn(
            decision=Decision(kind="tool", tool_name=name, tool_args=tool_args),
            reasoning_text=reasoning_text,
        )

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return ParsedModelTurn(
            decision=Decision(kind="final", assistant_message=content.strip()),
            reasoning_text=reasoning_text,
        )
    return ParsedModelTurn(
        decision=Decision(
            kind="final",
            assistant_message="DeepSeek returned an empty response.",
        ),
        reasoning_text=reasoning_text,
    )


def _open_tool_loop_assistant_id(session: Session) -> str | None:
    if not session.messages or session.messages[-1].role != "tool":
        return None
    index = len(session.messages) - 1
    while index >= 0 and session.messages[index].role == "tool":
        index -= 1
    if index < 0:
        return None
    candidate = session.messages[index]
    if candidate.role == "assistant" and candidate.tool_calls:
        return candidate.id
    return None


def _reasoning_for_message(session: Session, message_id: str) -> str | None:
    for message in session.messages:
        if message.id == message_id and message.reasoning_text:
            return message.reasoning_text
    return None


def _inject_reasoning_on_assistant(
    wire: list[dict[str, Any]],
    reasoning: str,
) -> list[dict[str, Any]]:
    """Attach ``reasoning_content`` to the last assistant message with tool_calls."""

    out: list[dict[str, Any]] = []
    injected = False
    for index in range(len(wire) - 1, -1, -1):
        msg = wire[index]
        if (
            not injected
            and msg.get("role") == "assistant"
            and msg.get("tool_calls")
        ):
            updated = dict(msg)
            updated["reasoning_content"] = reasoning
            out.insert(0, updated)
            injected = True
            continue
        out.insert(0, msg)
    return out if injected else wire
