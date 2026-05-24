"""Tests for OpenAI Responses transport (Post-MVP P4)."""

from __future__ import annotations

import json

import httpx
import pytest

from harnesslab.core.compaction import ModelOverflowError
from harnesslab.providers.transports.openai_responses import (
    OpenAIResponsesTransport,
    is_context_overflow_body,
)


def _transport(payload: dict, status_code: int = 200) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=payload)

    return httpx.MockTransport(handler)


def test_create_response_returns_model_dump_shape() -> None:
    payload = {
        "id": "resp_1",
        "object": "response",
        "status": "completed",
        "model": "gpt-5-mini",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ok"}],
            }
        ],
        "usage": {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
    }
    transport = OpenAIResponsesTransport(
        api_key="test-key",
        httpx_transport=_transport(payload),
    )
    result = transport.create_response(
        {
            "model": "gpt-5-mini",
            "input": [{"role": "user", "content": "hi"}],
        }
    )
    assert result["output"][0]["content"][0]["text"] == "ok"


def test_create_response_sends_reasoning_and_tools() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "id": "resp_1",
                "object": "response",
                "status": "completed",
                "model": "gpt-5-mini",
                "output": [],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        httpx_transport=httpx.MockTransport(handler),
    )
    transport.create_response(
        {
            "model": "gpt-5-mini",
            "instructions": "You are helpful.",
            "input": [{"role": "user", "content": "hi"}],
            "reasoning": {"effort": "medium"},
            "tools": [
                {
                    "type": "function",
                    "name": "grep",
                    "description": "search",
                    "parameters": {"type": "object"},
                    "strict": False,
                }
            ],
            "tool_choice": "auto",
        }
    )
    assert captured["model"] == "gpt-5-mini"
    assert captured["instructions"] == "You are helpful."
    assert captured["reasoning"] == {"effort": "medium"}
    assert captured["tools"][0]["name"] == "grep"


def test_create_response_raises_overflow() -> None:
    transport = OpenAIResponsesTransport(
        api_key="test-key",
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
    with pytest.raises(ModelOverflowError, match="too long"):
        transport.create_response(
            {
                "model": "gpt-5-mini",
                "input": [{"role": "user", "content": "hi"}],
            }
        )


def test_is_context_overflow_body() -> None:
    assert is_context_overflow_body(
        {"error": {"code": "context_length_exceeded", "message": "too long"}}
    )
