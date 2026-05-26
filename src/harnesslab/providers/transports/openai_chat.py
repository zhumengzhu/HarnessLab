"""OpenAI Chat Completions transport (SDK-backed)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI
from openai import APIStatusError as OpenAIAPIStatusError

from harnesslab.core.compaction import ModelOverflowError

_OVERFLOW_HINTS = (
    "context_length_exceeded",
    "context length exceeded",
    "maximum context length",
    "too many tokens",
)


class OpenAIChatTransport:
    """Thin wrapper around ``openai.OpenAI`` chat completions."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        httpx_transport: httpx.BaseTransport | None = None,
        client: OpenAI | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            return
        http_client = httpx.Client(
            transport=httpx_transport,
            timeout=timeout_seconds,
        )
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            http_client=http_client,
            timeout=timeout_seconds,
        )

    def create_chat_completion(self, body: dict[str, Any]) -> dict[str, Any]:
        """Execute one chat completion; return a JSON-like response dict."""

        kwargs: dict[str, Any] = {
            "model": body["model"],
            "messages": body["messages"],
        }
        tools = body.get("tools")
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = body.get("tool_choice", "auto")
        extra_body: dict[str, Any] = {}
        thinking = body.get("thinking")
        if thinking is not None:
            extra_body["thinking"] = thinking
        reasoning_effort = body.get("reasoning_effort")
        if reasoning_effort is not None:
            extra_body["reasoning_effort"] = reasoning_effort
        if extra_body:
            kwargs["extra_body"] = extra_body
        if "temperature" in body:
            kwargs["temperature"] = body["temperature"]
        elif thinking is None or thinking.get("type") == "disabled":
            kwargs["temperature"] = 0

        try:
            response = self._client.chat.completions.create(**kwargs)
        except OpenAIAPIStatusError as exc:
            if is_context_overflow_error(exc):
                raise ModelOverflowError(overflow_message_from_error(exc)) from exc
            raise
        except (APIConnectionError, APITimeoutError):
            raise

        return response.model_dump()

    def create_chat_completion_stream(
        self,
        body: dict[str, Any],
        *,
        on_delta: Callable[[str, str], None],
    ) -> dict[str, Any]:
        """Stream one chat completion; invoke ``on_delta(kind, text)`` per chunk."""

        kwargs: dict[str, Any] = {
            "model": body["model"],
            "messages": body["messages"],
            "stream": True,
        }
        tools = body.get("tools")
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = body.get("tool_choice", "auto")
        extra_body: dict[str, Any] = {}
        thinking = body.get("thinking")
        if thinking is not None:
            extra_body["thinking"] = thinking
        reasoning_effort = body.get("reasoning_effort")
        if reasoning_effort is not None:
            extra_body["reasoning_effort"] = reasoning_effort
        if extra_body:
            kwargs["extra_body"] = extra_body
        if "temperature" in body:
            kwargs["temperature"] = body["temperature"]
        elif thinking is None or thinking.get("type") == "disabled":
            kwargs["temperature"] = 0

        try:
            stream = self._client.chat.completions.create(**kwargs)
        except OpenAIAPIStatusError as exc:
            if is_context_overflow_error(exc):
                raise ModelOverflowError(overflow_message_from_error(exc)) from exc
            raise
        except (APIConnectionError, APITimeoutError):
            raise

        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] | None = None

        for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else None
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            reasoning_piece = getattr(delta, "reasoning_content", None)
            if isinstance(reasoning_piece, str) and reasoning_piece:
                on_delta("reasoning", reasoning_piece)
                reasoning_parts.append(reasoning_piece)
            if isinstance(delta.content, str) and delta.content:
                on_delta("assistant", delta.content)
                content_parts.append(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    entry = tool_calls_acc.setdefault(
                        idx,
                        {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        },
                    )
                    if tc.id:
                        entry["id"] = tc.id
                    fn = tc.function
                    if fn is not None:
                        if fn.name:
                            entry["function"]["name"] = (
                                entry["function"]["name"] + fn.name
                            )
                        if fn.arguments:
                            entry["function"]["arguments"] = (
                                entry["function"]["arguments"] + fn.arguments
                            )

        message: dict[str, Any] = {}
        reasoning_text = "".join(reasoning_parts).strip()
        content_text = "".join(content_parts).strip()
        if reasoning_text:
            message["reasoning_content"] = reasoning_text
        if content_text:
            message["content"] = content_text
        if tool_calls_acc:
            message["tool_calls"] = [
                tool_calls_acc[i] for i in sorted(tool_calls_acc)
            ]

        payload: dict[str, Any] = {"choices": [{"message": message}]}
        if usage:
            payload["usage"] = usage
        return payload


def is_context_overflow_error(exc: OpenAIAPIStatusError) -> bool:
    return is_context_overflow_body(exc.body)


def is_context_overflow_body(body: object) -> bool:
    error = _error_dict(body)
    if error is None:
        return False
    code = (error.get("code") or "").lower()
    msg = (error.get("message") or "").lower()
    return any(hint in code or hint in msg for hint in _OVERFLOW_HINTS)


def overflow_message_from_error(exc: OpenAIAPIStatusError) -> str:
    return overflow_message_from_body(exc.body)


def overflow_message_from_body(body: object) -> str:
    error = _error_dict(body)
    if isinstance(error, dict) and error.get("message"):
        return f"DeepSeek context length exceeded: {error['message']}"
    return "DeepSeek context length exceeded"


def _error_dict(body: object) -> dict | None:
    if not isinstance(body, dict):
        return None
    nested = body.get("error")
    if isinstance(nested, dict):
        return nested
    if "code" in body or "message" in body:
        return body
    return None
