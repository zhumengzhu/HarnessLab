"""Tests for Anthropic SDK Messages transport (Post-MVP P3)."""

from __future__ import annotations

import json

import httpx
import pytest
from anthropic import APIStatusError

from harnesslab.core.compaction import ModelOverflowError
from harnesslab.providers.transports.anthropic_messages import (
    AnthropicMessagesTransport,
    is_context_overflow_body,
    overflow_message_from_body,
)


def _transport(payload: dict, status_code: int = 200) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=payload)

    return httpx.MockTransport(handler)


def test_create_message_returns_model_dump_shape() -> None:
    payload = {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "ok"}],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 3, "output_tokens": 1},
    }
    transport = AnthropicMessagesTransport(
        api_key="test-key",
        httpx_transport=_transport(payload),
    )
    result = transport.create_message(
        {
            "model": "claude-sonnet-4-6",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert result["content"][0]["text"] == "ok"
    assert result["usage"]["input_tokens"] == 3


def test_create_message_sends_thinking_and_tools() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "id": "msg_01",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "model": "claude-sonnet-4-6",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    transport = AnthropicMessagesTransport(
        api_key="test-key",
        httpx_transport=httpx.MockTransport(handler),
    )
    transport.create_message(
        {
            "model": "claude-sonnet-4-6",
            "max_tokens": 1024,
            "system": "You are helpful.",
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"},
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {
                    "name": "grep",
                    "description": "search",
                    "input_schema": {"type": "object"},
                }
            ],
            "tool_choice": {"type": "auto"},
        }
    )
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["system"] == "You are helpful."
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"] == {"effort": "medium"}
    assert captured["tools"][0]["name"] == "grep"
    assert captured["tool_choice"] == {"type": "auto"}


def test_create_message_raises_overflow() -> None:
    transport = AnthropicMessagesTransport(
        api_key="test-key",
        httpx_transport=_transport(
            {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "prompt is too long",
                },
            },
            status_code=400,
        ),
    )
    with pytest.raises(ModelOverflowError, match="prompt is too long"):
        transport.create_message(
            {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "hi"}],
            }
        )


def test_create_message_propagates_non_overflow_400() -> None:
    transport = AnthropicMessagesTransport(
        api_key="test-key",
        httpx_transport=_transport(
            {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "bad arg",
                },
            },
            status_code=400,
        ),
    )
    with pytest.raises(APIStatusError):
        transport.create_message(
            {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "hi"}],
            }
        )


def test_create_message_sends_base_url_to_client() -> None:
    captured_url: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_url.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "id": "msg_01",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "model": "deepseek-v4-flash",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    transport = AnthropicMessagesTransport(
        api_key="test-key",
        base_url="https://api.deepseek.com/anthropic",
        httpx_transport=httpx.MockTransport(handler),
    )
    transport.create_message(
        {
            "model": "deepseek-v4-flash",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert captured_url
    assert captured_url[0].startswith("https://api.deepseek.com/anthropic/")


def test_is_context_overflow_body() -> None:
    body = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "prompt is too long"},
    }
    assert is_context_overflow_body(body) is True
    assert "prompt is too long" in overflow_message_from_body(body)
