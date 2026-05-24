"""OpenAI Responses API transport (SDK-backed, Post-MVP P4)."""

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
    "prompt is too long",
)


class OpenAIResponsesTransport:
    """Thin wrapper around ``openai.OpenAI`` Responses API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
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
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "http_client": http_client,
            "timeout": timeout_seconds,
        }
        if base_url:
            client_kwargs["base_url"] = base_url.rstrip("/")
        self._client = OpenAI(**client_kwargs)

    def create_response(self, body: dict[str, Any]) -> dict[str, Any]:
        """Execute one Responses call; return a JSON-like response dict."""

        kwargs: dict[str, Any] = {
            "model": body["model"],
            "input": body["input"],
        }
        instructions = body.get("instructions")
        if isinstance(instructions, str) and instructions.strip():
            kwargs["instructions"] = instructions
        reasoning = body.get("reasoning")
        if reasoning is not None:
            kwargs["reasoning"] = reasoning
        max_output_tokens = body.get("max_output_tokens")
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = max_output_tokens
        tools = body.get("tools")
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = body.get("tool_choice", "auto")

        try:
            response = self._client.responses.create(**kwargs)
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
        return f"OpenAI context length exceeded: {error['message']}"
    return "OpenAI context length exceeded"


def _error_dict(body: object) -> dict | None:
    if not isinstance(body, dict):
        return None
    nested = body.get("error")
    if isinstance(nested, dict):
        return nested
    if "code" in body or "message" in body:
        return body
    return None
