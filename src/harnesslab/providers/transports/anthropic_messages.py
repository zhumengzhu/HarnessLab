"""Anthropic Messages API transport (SDK-backed, Post-MVP P3)."""

from __future__ import annotations

from typing import Any

import httpx
from anthropic import Anthropic, APIConnectionError, APITimeoutError
from anthropic import APIStatusError as AnthropicAPIStatusError

from harnesslab.core.compaction import ModelOverflowError

_OVERFLOW_HINTS = (
    "prompt is too long",
    "context window",
    "maximum context",
    "too many tokens",
    "context_length",
)


class AnthropicMessagesTransport:
    """Thin wrapper around ``anthropic.Anthropic`` Messages API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        httpx_transport: httpx.BaseTransport | None = None,
        client: Anthropic | None = None,
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
        self._client = Anthropic(**client_kwargs)

    def create_message(self, body: dict[str, Any]) -> dict[str, Any]:
        """Execute one Messages call; return a JSON-like response dict."""

        kwargs: dict[str, Any] = {
            "model": body["model"],
            "max_tokens": body.get("max_tokens", 8192),
            "messages": body["messages"],
        }
        system = body.get("system")
        if isinstance(system, str) and system.strip():
            kwargs["system"] = system
        thinking = body.get("thinking")
        if thinking is not None:
            kwargs["thinking"] = thinking
        output_config = body.get("output_config")
        if output_config is not None:
            kwargs["output_config"] = output_config
        tools = body.get("tools")
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = body.get("tool_choice", {"type": "auto"})

        try:
            response = self._client.messages.create(**kwargs)
        except AnthropicAPIStatusError as exc:
            if is_context_overflow_error(exc):
                raise ModelOverflowError(overflow_message_from_error(exc)) from exc
            raise
        except (APIConnectionError, APITimeoutError):
            raise

        return response.model_dump()


def is_context_overflow_error(exc: AnthropicAPIStatusError) -> bool:
    return is_context_overflow_body(exc.body)


def is_context_overflow_body(body: object) -> bool:
    error = _error_dict(body)
    if error is None:
        return False
    error_type = (error.get("type") or "").lower()
    msg = (error.get("message") or "").lower()
    return any(hint in error_type or hint in msg for hint in _OVERFLOW_HINTS)


def overflow_message_from_error(exc: AnthropicAPIStatusError) -> str:
    return overflow_message_from_body(exc.body)


def overflow_message_from_body(body: object) -> str:
    error = _error_dict(body)
    if isinstance(error, dict) and error.get("message"):
        return f"Anthropic context length exceeded: {error['message']}"
    return "Anthropic context length exceeded"


def _error_dict(body: object) -> dict | None:
    if not isinstance(body, dict):
        return None
    nested = body.get("error")
    if isinstance(nested, dict):
        return nested
    if "type" in body or "message" in body:
        return body
    return None
