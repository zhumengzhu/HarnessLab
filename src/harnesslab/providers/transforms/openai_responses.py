"""OpenAI Responses API transform (Post-MVP P4)."""

from __future__ import annotations

import json
from typing import Any

from harnesslab.core.models import Decision, Session
from harnesslab.core.prompt import ComposedPrompt
from harnesslab.providers.catalog import CatalogEntry
from harnesslab.providers.transforms.types import ParsedModelTurn, ReplayPolicy

_REASONING_ITEMS_KEY = "reasoning_items"


def replay_policy(session: Session, entry: CatalogEntry) -> ReplayPolicy:
    """Decide whether reasoning output items must replay on the wire."""

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


def serialize_request(
    composed: ComposedPrompt,
    session: Session,
    entry: CatalogEntry,
) -> dict[str, Any]:
    """Build Responses API ``instructions`` + ``input`` from composed prompt."""

    openai_wire = composed.as_openai_messages()
    instructions_parts: list[str] = []
    input_items: list[dict[str, Any]] = []

    for msg in openai_wire:
        role = msg.get("role")
        if role == "system":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                instructions_parts.append(content.strip())
            continue
        if role == "user":
            content = msg.get("content")
            input_items.append(
                {
                    "role": "user",
                    "content": content if isinstance(content, str) else str(content or ""),
                }
            )
        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    function = tc.get("function", {})
                    if not isinstance(function, dict):
                        continue
                    name = function.get("name")
                    if not isinstance(name, str) or not name:
                        continue
                    arguments = function.get("arguments", "{}")
                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments)
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": tc.get("id") or "call_placeholder",
                            "name": name,
                            "arguments": arguments,
                        }
                    )
            else:
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    input_items.append({"role": "assistant", "content": content.strip()})
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call_id,
                        "output": msg.get("content") or "",
                    }
                )

    policy = replay_policy(session, entry)
    if policy.include_reasoning_in_tool_loop:
        assistant_id = _open_tool_loop_assistant_id(session)
        if assistant_id is not None:
            reasoning_items = _reasoning_items_for_message(session, assistant_id)
            if reasoning_items:
                input_items = _inject_reasoning_items(input_items, reasoning_items)

    return {
        "instructions": "\n\n".join(instructions_parts) if instructions_parts else None,
        "input": input_items,
    }


def parse_response(
    payload: dict[str, Any],
    entry: CatalogEntry | None = None,
) -> ParsedModelTurn:
    """Translate one Responses API payload into a normalized turn."""

    _ = entry
    output = payload.get("output")
    if not isinstance(output, list):
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="OpenAI response invalid: missing output.",
            )
        )

    reasoning_items: list[dict[str, Any]] = []
    reasoning_parts: list[str] = []

    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "reasoning":
            reasoning_items.append(dict(item))
            for block in item.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "reasoning_text":
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        reasoning_parts.append(text.strip())
            for summary in item.get("summary") or []:
                if isinstance(summary, dict):
                    text = summary.get("text")
                    if isinstance(text, str) and text.strip():
                        reasoning_parts.append(text.strip())
        elif item_type == "function_call":
            name = item.get("name")
            arguments = item.get("arguments")
            if not isinstance(name, str) or not name:
                return ParsedModelTurn(
                    decision=Decision(
                        kind="final",
                        assistant_message="OpenAI function_call invalid: missing name.",
                    ),
                    reasoning_text=_join_reasoning(reasoning_parts),
                    provider_extra=_reasoning_extra(reasoning_items),
                )
            if not isinstance(arguments, str):
                return ParsedModelTurn(
                    decision=Decision(
                        kind="final",
                        assistant_message=(
                            "OpenAI function_call invalid: arguments must be a string."
                        ),
                    ),
                    reasoning_text=_join_reasoning(reasoning_parts),
                    provider_extra=_reasoning_extra(reasoning_items),
                )
            try:
                tool_args = json.loads(arguments)
            except json.JSONDecodeError as exc:
                return ParsedModelTurn(
                    decision=Decision(
                        kind="final",
                        assistant_message=f"OpenAI function_call invalid JSON args: {exc.msg}",
                    ),
                    reasoning_text=_join_reasoning(reasoning_parts),
                    provider_extra=_reasoning_extra(reasoning_items),
                )
            if not isinstance(tool_args, dict):
                return ParsedModelTurn(
                    decision=Decision(
                        kind="final",
                        assistant_message=(
                            "OpenAI function_call invalid: JSON args must be an object."
                        ),
                    ),
                    reasoning_text=_join_reasoning(reasoning_parts),
                    provider_extra=_reasoning_extra(reasoning_items),
                )
            return ParsedModelTurn(
                decision=Decision(kind="tool", tool_name=name, tool_args=tool_args),
                reasoning_text=_join_reasoning(reasoning_parts),
                provider_extra=_reasoning_extra(reasoning_items),
            )

    text_parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for block in item.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "output_text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())

    if text_parts:
        return ParsedModelTurn(
            decision=Decision(kind="final", assistant_message="\n".join(text_parts)),
            reasoning_text=_join_reasoning(reasoning_parts),
            provider_extra=_reasoning_extra(reasoning_items),
        )

    return ParsedModelTurn(
        decision=Decision(
            kind="final",
            assistant_message="OpenAI returned an empty response.",
        ),
        reasoning_text=_join_reasoning(reasoning_parts),
        provider_extra=_reasoning_extra(reasoning_items),
    )


def _join_reasoning(parts: list[str]) -> str | None:
    if not parts:
        return None
    return "\n".join(parts)


def _reasoning_extra(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return {_REASONING_ITEMS_KEY: items}


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


def _reasoning_items_for_message(session: Session, message_id: str) -> list[dict[str, Any]]:
    for message in session.messages:
        if message.id != message_id:
            continue
        extra = message.provider_extra
        if isinstance(extra, dict):
            items = extra.get(_REASONING_ITEMS_KEY)
            if isinstance(items, list) and items:
                return [dict(i) for i in items if isinstance(i, dict)]
    return []


def _inject_reasoning_items(
    input_items: list[dict[str, Any]],
    reasoning_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Insert reasoning items immediately before the last function_call block."""

    insert_at = None
    for index in range(len(input_items) - 1, -1, -1):
        if input_items[index].get("type") == "function_call":
            insert_at = index
            break
    if insert_at is None:
        return input_items
    return (
        input_items[:insert_at]
        + [dict(item) for item in reasoning_items]
        + input_items[insert_at:]
    )
