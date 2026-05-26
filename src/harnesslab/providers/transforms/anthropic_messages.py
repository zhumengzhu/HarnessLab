"""Anthropic Messages API transform (Post-MVP P3)."""

from __future__ import annotations

import json
from typing import Any

from harnesslab.core.models import Decision, Session
from harnesslab.core.prompt import ComposedPrompt
from harnesslab.providers.catalog import CatalogEntry
from harnesslab.providers.transforms.types import ParsedModelTurn, ReplayPolicy

_THINKING_BLOCKS_KEY = "thinking_blocks"


def replay_policy(session: Session, entry: CatalogEntry) -> ReplayPolicy:
    """Decide whether assistant thinking blocks must replay on the wire."""

    if entry.reasoning_support == "none":
        return ReplayPolicy(
            include_reasoning_in_tool_loop=False,
            drop_reasoning_on_new_user_turn=True,
        )
    in_tool_loop = bool(session.messages and session.messages[-1].role == "tool")
    has_persisted = _session_has_tool_reasoning(session)
    return ReplayPolicy(
        include_reasoning_in_tool_loop=in_tool_loop or has_persisted,
        drop_reasoning_on_new_user_turn=not has_persisted,
    )


def serialize_messages(
    composed: ComposedPrompt,
    session: Session,
    entry: CatalogEntry,
) -> dict[str, Any]:
    """Build Anthropic request fields from composed prompt + session."""

    openai_wire = composed.as_openai_messages()
    system, messages = _openai_messages_to_anthropic(openai_wire)
    if entry.reasoning_support != "none":
        messages = _inject_all_thinking_blocks(messages, session)
    return {"system": system, "messages": messages}


def parse_response(
    payload: dict[str, Any],
    entry: CatalogEntry | None = None,
) -> ParsedModelTurn:
    """Translate one Messages API response into a normalized turn."""

    _ = entry
    content = payload.get("content")
    if not isinstance(content, list):
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="Anthropic response invalid: missing content.",
            )
        )

    thinking_blocks: list[dict[str, Any]] = []
    reasoning_parts: list[str] = []
    text_parts: list[str] = []
    tool_uses: list[dict[str, Any]] = []

    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "thinking":
            thinking_blocks.append(dict(block))
            thinking_text = block.get("thinking")
            if isinstance(thinking_text, str) and thinking_text.strip():
                reasoning_parts.append(thinking_text.strip())
        elif block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
        elif block_type == "tool_use":
            tool_uses.append(block)

    reasoning_text = "\n".join(reasoning_parts) if reasoning_parts else None
    provider_extra = (
        {_THINKING_BLOCKS_KEY: thinking_blocks} if thinking_blocks else None
    )

    if tool_uses:
        first = tool_uses[0]
        name = first.get("name")
        tool_input = first.get("input")
        if not isinstance(name, str) or not name:
            return ParsedModelTurn(
                decision=Decision(
                    kind="final",
                    assistant_message="Anthropic tool_use invalid: missing name.",
                ),
                reasoning_text=reasoning_text,
                provider_extra=provider_extra,
            )
        if not isinstance(tool_input, dict):
            return ParsedModelTurn(
                decision=Decision(
                    kind="final",
                    assistant_message="Anthropic tool_use invalid: input must be an object.",
                ),
                reasoning_text=reasoning_text,
                provider_extra=provider_extra,
            )
        return ParsedModelTurn(
            decision=Decision(kind="tool", tool_name=name, tool_args=tool_input),
            reasoning_text=reasoning_text,
            provider_extra=provider_extra,
        )

    if text_parts:
        return ParsedModelTurn(
            decision=Decision(kind="final", assistant_message="\n".join(text_parts)),
            reasoning_text=reasoning_text,
            provider_extra=provider_extra,
        )

    return ParsedModelTurn(
        decision=Decision(
            kind="final",
            assistant_message="Anthropic returned an empty response.",
        ),
        reasoning_text=reasoning_text,
        provider_extra=provider_extra,
    )


def _openai_messages_to_anthropic(
    openai_wire: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
    pending_tool_results: list[dict[str, Any]] = []

    def flush_tool_results() -> None:
        if pending_tool_results:
            out.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

    for msg in openai_wire:
        role = msg.get("role")
        if role == "system":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                system_parts.append(content.strip())
            continue
        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if not isinstance(tool_call_id, str) or not tool_call_id:
                continue
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": msg.get("content") or "",
                }
            )
            continue
        flush_tool_results()
        if role == "user":
            content = msg.get("content")
            out.append(
                {
                    "role": "user",
                    "content": content if isinstance(content, str) else str(content or ""),
                }
            )
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            text = msg.get("content")
            if isinstance(text, str) and text.strip():
                blocks.append({"type": "text", "text": text.strip()})
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    function = tc.get("function", {})
                    if not isinstance(function, dict):
                        continue
                    name = function.get("name")
                    if not isinstance(name, str) or not name:
                        continue
                    raw_args = function.get("arguments", "{}")
                    tool_input: dict[str, Any]
                    if isinstance(raw_args, str):
                        try:
                            parsed = json.loads(raw_args)
                        except json.JSONDecodeError:
                            parsed = {}
                        tool_input = parsed if isinstance(parsed, dict) else {}
                    elif isinstance(raw_args, dict):
                        tool_input = raw_args
                    else:
                        tool_input = {}
                    tool_id = tc.get("id")
                    if not isinstance(tool_id, str) or not tool_id:
                        tool_id = "toolu_placeholder"
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": name,
                            "input": tool_input,
                        }
                    )
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            elif isinstance(text, str):
                out.append({"role": "assistant", "content": text})

    flush_tool_results()
    system = "\n\n".join(system_parts) if system_parts else None
    return system, out


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


def _thinking_blocks_for_message(session: Session, message_id: str) -> list[dict[str, Any]]:
    for message in session.messages:
        if message.id != message_id:
            continue
        extra = message.provider_extra
        if isinstance(extra, dict):
            blocks = extra.get(_THINKING_BLOCKS_KEY)
            if isinstance(blocks, list) and blocks:
                return [dict(b) for b in blocks if isinstance(b, dict)]
        if message.reasoning_text:
            return [{"type": "thinking", "thinking": message.reasoning_text}]
    return []


def _session_has_tool_reasoning(session: Session) -> bool:
    for message in session.messages:
        if message.role != "assistant" or not message.tool_calls:
            continue
        if _thinking_blocks_for_message(session, message.id):
            return True
    return False


def _inject_all_thinking_blocks(
    messages: list[dict[str, Any]],
    session: Session,
) -> list[dict[str, Any]]:
    """Prepend thinking blocks to every assistant turn that includes tool_use."""

    thinking_by_order = [
        _thinking_blocks_for_message(session, message.id)
        for message in session.messages
        if message.role == "assistant" and message.tool_calls
    ]
    if not any(thinking_by_order):
        return messages

    idx = 0
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") != "assistant" or idx >= len(thinking_by_order):
            out.append(msg)
            continue
        content = msg.get("content")
        if not isinstance(content, list) or not any(
            isinstance(block, dict) and block.get("type") == "tool_use" for block in content
        ):
            out.append(msg)
            continue
        blocks = thinking_by_order[idx]
        idx += 1
        if not blocks:
            out.append(msg)
            continue
        merged = [dict(block) for block in blocks] + [
            dict(block) for block in content if isinstance(block, dict)
        ]
        out.append({"role": "assistant", "content": merged})
    return out


def _inject_thinking_blocks(
    messages: list[dict[str, Any]],
    thinking_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prepend thinking blocks to the last assistant message with tool_use."""

    out: list[dict[str, Any]] = []
    injected = False
    for index in range(len(messages) - 1, -1, -1):
        msg = messages[index]
        if not injected and msg.get("role") == "assistant":
            content = msg.get("content")
            if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_use" for b in content
            ):
                merged = [dict(b) for b in thinking_blocks] + [
                    dict(b) for b in content if isinstance(b, dict)
                ]
                out.insert(0, {"role": "assistant", "content": merged})
                injected = True
                continue
        out.insert(0, msg)
    return out if injected else messages
