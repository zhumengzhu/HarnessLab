"""Tests for OpenAI SDK chat transport (Post-MVP P2)."""

from __future__ import annotations

import json

import httpx
import pytest
from openai import APIStatusError

from harnesslab.core.compaction import ModelOverflowError
from harnesslab.providers.transports.openai_chat import (
    OpenAIChatTransport,
    is_context_overflow_body,
    overflow_message_from_body,
)


def _transport(payload: dict, status_code: int = 200) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=payload)

    return httpx.MockTransport(handler)


def test_create_chat_completion_returns_model_dump_shape() -> None:
    payload = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }
    transport = OpenAIChatTransport(
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        httpx_transport=_transport(payload),
    )
    result = transport.create_chat_completion(
        {
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0,
        }
    )
    assert result["choices"][0]["message"]["content"] == "ok"
    assert result["usage"]["prompt_tokens"] == 3


def test_create_chat_completion_sends_thinking_via_extra_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    transport = OpenAIChatTransport(
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        httpx_transport=httpx.MockTransport(handler),
    )
    transport.create_chat_completion(
        {
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "disabled"},
            "tools": [{"type": "function", "function": {"name": "grep", "parameters": {}}}],
            "tool_choice": "auto",
        }
    )
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["thinking"] == {"type": "disabled"}
    assert captured["tool_choice"] == "auto"
    assert captured["tools"][0]["function"]["name"] == "grep"


def test_create_chat_completion_raises_overflow() -> None:
    transport = OpenAIChatTransport(
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        httpx_transport=_transport(
            {
                "error": {
                    "code": "context_length_exceeded",
                    "message": "too long",
                }
            },
            status_code=400,
        ),
    )
    with pytest.raises(ModelOverflowError, match="context length exceeded"):
        transport.create_chat_completion(
            {
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "hi"}],
            }
        )


def test_create_chat_completion_propagates_non_overflow_400() -> None:
    transport = OpenAIChatTransport(
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        httpx_transport=_transport(
            {"error": {"code": "invalid_request_error", "message": "bad arg"}},
            status_code=400,
        ),
    )
    with pytest.raises(APIStatusError):
        transport.create_chat_completion(
            {
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "hi"}],
            }
        )


def test_is_context_overflow_body_handles_nested_and_flat_shapes() -> None:
    nested = {"error": {"code": "context_length_exceeded", "message": "too long"}}
    flat = {"code": "context_length_exceeded", "message": "too long"}
    assert is_context_overflow_body(nested) is True
    assert is_context_overflow_body(flat) is True
    assert "too long" in overflow_message_from_body(flat)
