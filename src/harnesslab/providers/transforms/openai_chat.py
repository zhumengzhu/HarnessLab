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
    has_persisted = _session_has_assistant_reasoning(session)
    return ReplayPolicy(
        include_reasoning_in_tool_loop=in_tool_loop or has_persisted,
        drop_reasoning_on_new_user_turn=not has_persisted,
    )


def serialize_messages(
    composed: ComposedPrompt,
    session: Session,
    entry: CatalogEntry,
) -> list[dict[str, Any]]:
    """Build OpenAI-style messages, applying replay policy for reasoning."""

    if entry.reasoning_support == "none":
        return composed.as_openai_messages()
    return composed.as_openai_messages(
        reasoning_by_message_id=_reasoning_by_message_id(session, entry),
    )


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
    if not isinstance(reasoning_raw, str) or not reasoning_raw.strip():
        for key in ("reasoning", "reasoning_text"):
            alt = message.get(key)
            if isinstance(alt, str) and alt.strip():
                reasoning_raw = alt
                break
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


def _session_has_assistant_reasoning(session: Session) -> bool:
    return any(
        m.role == "assistant" and m.reasoning_text and m.reasoning_text.strip()
        for m in session.messages
    )


def _reasoning_by_message_id(session: Session, entry: CatalogEntry) -> dict[str, str]:
    """Map assistant message ids to wire ``reasoning_content``.

    In thinking mode, tool assistants without captured reasoning still get an
    empty string so DeepSeek receives the required field on replay.
    """

    out: dict[str, str] = {}
    thinking_replay = entry.reasoning_support != "none"
    for message in session.messages:
        if message.role != "assistant":
            continue
        text = message.reasoning_text
        if isinstance(text, str) and text.strip():
            out[message.id] = text.strip()
            continue
        if thinking_replay and message.tool_calls:
            out[message.id] = ""
    return out
