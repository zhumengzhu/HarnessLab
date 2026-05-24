"""OpenAI Chat Completions transport (SDK-backed)."""

from __future__ import annotations

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
            "temperature": body.get("temperature", 0),
        }
        tools = body.get("tools")
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = body.get("tool_choice", "auto")
        extra_body: dict[str, Any] = {}
        thinking = body.get("thinking")
        if thinking is not None:
            extra_body["thinking"] = thinking
        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            response = self._client.chat.completions.create(**kwargs)
        except OpenAIAPIStatusError as exc:
            if is_context_overflow_error(exc):
                raise ModelOverflowError(overflow_message_from_error(exc)) from exc
            raise
        except (APIConnectionError, APITimeoutError):
            raise

        return response.model_dump()


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
