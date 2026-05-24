"""Unit tests for AnthropicModel provider adapter (Post-MVP P3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from harnesslab.core.models import Message, Session
from harnesslab.providers.anthropic import DEEPSEEK_ANTHROPIC_BASE_URL, AnthropicModel


def _session() -> Session:
    return Session(
        id="ses_test",
        goal="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[
            Message(
                id="msg_1",
                role="user",
                content="hello",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                session_id="ses_test",
            )
        ],
    )


def _anthropic_response(content: list[dict], *, usage: dict | None = None) -> dict:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": usage or {"input_tokens": 10, "output_tokens": 2},
    }


def _transport(payload: dict, status_code: int = 200) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=payload)

    return httpx.MockTransport(handler)


def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicModel(tool_specs_provider=lambda: [])


def test_accepts_deepseek_key_with_anthropic_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    model = AnthropicModel(
        tool_specs_provider=lambda: [],
        base_url=DEEPSEEK_ANTHROPIC_BASE_URL,
        transport=_transport(
            _anthropic_response([{"type": "text", "text": "ok"}])
        ),
    )
    assert model.decide(_session(), "hi").kind == "final"


def test_deepseek_base_prefers_deepseek_key_over_anthropic_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "wrong-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    model = AnthropicModel(
        tool_specs_provider=lambda: [],
        base_url=DEEPSEEK_ANTHROPIC_BASE_URL,
        transport=_transport(
            _anthropic_response([{"type": "text", "text": "ok"}])
        ),
    )
    assert model.decide(_session(), "hi").kind == "final"


def test_returns_final_decision() -> None:
    model = AnthropicModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(
            _anthropic_response([{"type": "text", "text": "hi from claude"}])
        ),
    )
    decision = model.decide(_session(), "hello")
    assert decision.kind == "final"
    assert decision.assistant_message == "hi from claude"
    meta = model.last_call_meta()
    assert meta["provider"] == "anthropic"
    assert meta["api_family"] == "anthropic_messages"
    assert meta["model_name"] == "claude-sonnet-4-6"
    assert meta["request_tokens"] == 10
    assert meta["response_tokens"] == 2
    assert meta["total_tokens"] == 12


def test_returns_tool_decision() -> None:
    model = AnthropicModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(
            _anthropic_response(
                [
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "write_file",
                        "input": {"path": "a.txt", "content": "x"},
                    }
                ]
            )
        ),
    )
    decision = model.decide(_session(), "write")
    assert decision.kind == "tool"
    assert decision.tool_name == "write_file"
    assert decision.tool_args == {"path": "a.txt", "content": "x"}


def test_last_call_meta_includes_reasoning_and_provider_extra() -> None:
    thinking = {"type": "thinking", "thinking": "search first", "signature": "sig"}
    model = AnthropicModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(
            _anthropic_response(
                [
                    thinking,
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "grep",
                        "input": {"pattern": "x"},
                    },
                ]
            )
        ),
    )
    model.decide(_session(), "grep")
    meta = model.last_call_meta()
    assert meta["reasoning_text"] == "search first"
    assert meta["provider_extra"] == {"thinking_blocks": [thinking]}


def test_request_body_replays_thinking_blocks_in_open_tool_loop() -> None:
    captured: dict = {}
    thinking = {"type": "thinking", "thinking": "plan: grep foo", "signature": "sig"}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json=_anthropic_response([{"type": "text", "text": "done after tool"}]),
        )

    session = Session(
        id="ses_tool_loop",
        goal="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[
            Message(
                id="msg_u",
                role="user",
                content="run grep",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                session_id="ses_tool_loop",
            ),
            Message(
                id="msg_a",
                role="assistant",
                content="",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                session_id="ses_tool_loop",
                tool_calls=[
                    {
                        "id": "toolu_01",
                        "type": "function",
                        "function": {
                            "name": "grep",
                            "arguments": json.dumps({"pattern": "foo"}),
                        },
                    }
                ],
                provider_extra={"thinking_blocks": [thinking]},
            ),
            Message(
                id="msg_t",
                role="tool",
                content="[tool:grep] matches",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                session_id="ses_tool_loop",
                tool_call_id="toolu_01",
            ),
        ],
    )

    model = AnthropicModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=httpx.MockTransport(handler),
    )
    model.decide(session, "run grep")

    assistant_msgs = [
        m
        for m in captured["messages"]
        if m.get("role") == "assistant"
        and isinstance(m.get("content"), list)
        and any(b.get("type") == "tool_use" for b in m["content"])
    ]
    assert assistant_msgs
    assert assistant_msgs[-1]["content"][0] == thinking


def test_http_error_falls_back_to_final() -> None:
    model = AnthropicModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(
            {
                "type": "error",
                "error": {"type": "api_error", "message": "server down"},
            },
            status_code=500,
        ),
    )
    decision = model.decide(_session(), "hello")
    assert decision.kind == "final"
    assert "Anthropic request failed" in (decision.assistant_message or "")


def test_request_body_includes_user_input_when_session_has_no_messages() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json=_anthropic_response([{"type": "text", "text": "ok"}]),
        )

    model = AnthropicModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=httpx.MockTransport(handler),
    )
    empty = Session(
        id="ses_empty",
        goal="smoke",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[],
    )
    model.decide(empty, "hello from smoke")
    assert captured["messages"] == [{"role": "user", "content": "hello from smoke"}]
    assert isinstance(captured.get("system"), str)


def test_request_body_uses_system_and_anthropic_tools() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json=_anthropic_response([{"type": "text", "text": "ok"}]),
        )

    model = AnthropicModel(
        tool_specs_provider=lambda: [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "read",
                    "parameters": {"type": "object"},
                },
            }
        ],
        api_key="x",
        thinking_mode="adaptive",
        thinking_effort="medium",
        transport=httpx.MockTransport(handler),
    )
    model.decide(_session(), "hello")

    assert captured["model"] == "claude-sonnet-4-6"
    assert isinstance(captured.get("system"), str)
    assert "HarnessLab" in captured["system"]
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"] == {"effort": "medium"}
    assert captured["tools"][0]["name"] == "read_file"
    assert captured["tool_choice"] == {"type": "auto"}
