"""Google Gemini generateContent transform (Post-MVP P5)."""

from __future__ import annotations

import json
from typing import Any

from harnesslab.core.models import Decision, Session
from harnesslab.core.prompt import ComposedPrompt
from harnesslab.providers.catalog import CatalogEntry
from harnesslab.providers.transforms.types import ParsedModelTurn, ReplayPolicy

_THOUGHT_PARTS_KEY = "thought_parts"


def replay_policy(session: Session, entry: CatalogEntry) -> ReplayPolicy:
    """Decide whether Gemini thought parts must replay on the wire."""

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


def serialize_request(
    composed: ComposedPrompt,
    session: Session,
    entry: CatalogEntry,
) -> dict[str, Any]:
    """Build Gemini ``contents`` + optional ``system_instruction`` from prompt."""

    openai_wire = composed.as_openai_messages()
    system_instruction, contents = _openai_messages_to_gemini(openai_wire)
    if entry.reasoning_support != "none":
        contents = _inject_all_thought_parts(contents, session)
    return {
        "system_instruction": system_instruction,
        "contents": contents,
    }


def parse_response(
    payload: dict[str, Any],
    entry: CatalogEntry | None = None,
) -> ParsedModelTurn:
    """Translate one generateContent payload into a normalized turn."""

    _ = entry
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="Gemini response invalid: missing candidates.",
            )
        )

    first = candidates[0]
    if not isinstance(first, dict):
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="Gemini response invalid: candidate shape.",
            )
        )

    content = first.get("content")
    if not isinstance(content, dict):
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="Gemini response invalid: missing content.",
            )
        )

    parts = content.get("parts")
    if not isinstance(parts, list):
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="Gemini response invalid: missing parts.",
            )
        )

    thought_parts: list[dict[str, Any]] = []
    reasoning_parts: list[str] = []
    text_parts: list[str] = []
    function_calls: list[dict[str, Any]] = []

    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("thought") is True:
            thought_parts.append(dict(part))
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                reasoning_parts.append(text.strip())
            continue
        function_call = part.get("functionCall") or part.get("function_call")
        if isinstance(function_call, dict):
            function_calls.append(function_call)
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())

    reasoning_text = "\n".join(reasoning_parts) if reasoning_parts else None
    provider_extra = (
        {_THOUGHT_PARTS_KEY: thought_parts} if thought_parts else None
    )

    if function_calls:
        first_call = function_calls[0]
        name = first_call.get("name")
        args = first_call.get("args")
        if not isinstance(name, str) or not name:
            return ParsedModelTurn(
                decision=Decision(
                    kind="final",
                    assistant_message="Gemini functionCall invalid: missing name.",
                ),
                reasoning_text=reasoning_text,
                provider_extra=provider_extra,
            )
        tool_args: dict[str, Any]
        if isinstance(args, dict):
            tool_args = args
        else:
            tool_args = {}
        return ParsedModelTurn(
            decision=Decision(kind="tool", tool_name=name, tool_args=tool_args),
            reasoning_text=reasoning_text,
            provider_extra=provider_extra,
        )

    assistant_message = "\n".join(text_parts) if text_parts else ""
    if not assistant_message.strip():
        return ParsedModelTurn(
            decision=Decision(
                kind="final",
                assistant_message="Gemini response empty: no text or tool call.",
            ),
            reasoning_text=reasoning_text,
            provider_extra=provider_extra,
        )
    return ParsedModelTurn(
        decision=Decision(kind="final", assistant_message=assistant_message),
        reasoning_text=reasoning_text,
        provider_extra=provider_extra,
    )


def _openai_messages_to_gemini(
    messages: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    pending_tool_parts: list[dict[str, Any]] = []

    def flush_tool_parts() -> None:
        if pending_tool_parts:
            contents.append({"role": "user", "parts": list(pending_tool_parts)})
            pending_tool_parts.clear()

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                system_parts.append(content.strip())
            continue
        if role == "user":
            flush_tool_parts()
            content = msg.get("content")
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": content
                            if isinstance(content, str)
                            else str(content or "")
                        }
                    ],
                }
            )
        elif role == "assistant":
            flush_tool_parts()
            parts: list[dict[str, Any]] = []
            text = msg.get("content")
            if isinstance(text, str) and text.strip():
                parts.append({"text": text.strip()})
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
                    args: dict[str, Any]
                    if isinstance(raw_args, str):
                        try:
                            parsed = json.loads(raw_args)
                        except json.JSONDecodeError:
                            parsed = {}
                        args = parsed if isinstance(parsed, dict) else {}
                    elif isinstance(raw_args, dict):
                        args = raw_args
                    else:
                        args = {}
                    parts.append({"functionCall": {"name": name, "args": args}})
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            name = tool_call_id if isinstance(tool_call_id, str) else "tool"
            pending_tool_parts.append(
                {
                    "functionResponse": {
                        "name": name,
                        "response": {"result": msg.get("content") or ""},
                    }
                }
            )

    flush_tool_parts()
    system_instruction = (
        {"parts": [{"text": "\n\n".join(system_parts)}]} if system_parts else None
    )
    return system_instruction, contents


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


def _thought_parts_for_message(session: Session, message_id: str) -> list[dict[str, Any]]:
    for message in session.messages:
        if message.id != message_id:
            continue
        extra = message.provider_extra
        if isinstance(extra, dict):
            parts = extra.get(_THOUGHT_PARTS_KEY)
            if isinstance(parts, list) and parts:
                return [dict(p) for p in parts if isinstance(p, dict)]
        if message.reasoning_text:
            return [{"text": message.reasoning_text, "thought": True}]
    return []


def _session_has_tool_reasoning(session: Session) -> bool:
    for message in session.messages:
        if message.role != "assistant" or not message.tool_calls:
            continue
        if _thought_parts_for_message(session, message.id):
            return True
    return False


def _inject_all_thought_parts(
    contents: list[dict[str, Any]],
    session: Session,
) -> list[dict[str, Any]]:
    """Prepend thought parts to every model turn that includes a function call."""

    parts_by_order = [
        _thought_parts_for_message(session, message.id)
        for message in session.messages
        if message.role == "assistant" and message.tool_calls
    ]
    if not any(parts_by_order):
        return contents

    idx = 0
    out: list[dict[str, Any]] = []
    for msg in contents:
        if msg.get("role") != "model" or idx >= len(parts_by_order):
            out.append(msg)
            continue
        parts = msg.get("parts")
        if not isinstance(parts, list) or not any(
            isinstance(part, dict) and ("functionCall" in part or "function_call" in part)
            for part in parts
        ):
            out.append(msg)
            continue
        thought_parts = parts_by_order[idx]
        idx += 1
        if not thought_parts:
            out.append(msg)
            continue
        merged = [dict(part) for part in thought_parts] + [
            dict(part) for part in parts if isinstance(part, dict)
        ]
        out.append({"role": "model", "parts": merged})
    return out


def _inject_thought_parts(
    contents: list[dict[str, Any]],
    thought_parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prepend thought parts to the last model turn that includes a function call."""

    out: list[dict[str, Any]] = []
    injected = False
    for index in range(len(contents) - 1, -1, -1):
        msg = contents[index]
        if not injected and msg.get("role") == "model":
            parts = msg.get("parts")
            if isinstance(parts, list) and any(
                isinstance(p, dict) and ("functionCall" in p or "function_call" in p)
                for p in parts
            ):
                merged = [dict(p) for p in thought_parts] + [
                    dict(p) for p in parts if isinstance(p, dict)
                ]
                out.insert(0, {"role": "model", "parts": merged})
                injected = True
                continue
        out.insert(0, msg)
    return out if injected else contents
