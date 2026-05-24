"""Unit tests for OpenAIResponsesModel adapter (Post-MVP P4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from harnesslab.core.models import Message, Session
from harnesslab.providers.openai_responses import OpenAIResponsesModel


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


def _response_payload(output: list[dict], *, usage: dict | None = None) -> dict:
    return {
        "id": "resp_1",
        "object": "response",
        "status": "completed",
        "model": "gpt-5-mini",
        "output": output,
        "usage": usage
        or {
            "input_tokens": 10,
            "output_tokens": 2,
            "output_tokens_details": {"reasoning_tokens": 1},
        },
    }


def _transport(payload: dict, status_code: int = 200) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=payload)

    return httpx.MockTransport(handler)


def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIResponsesModel(tool_specs_provider=lambda: [])


def test_returns_final_decision() -> None:
    model = OpenAIResponsesModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(
            _response_payload(
                [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hi from openai"}],
                    }
                ]
            )
        ),
    )
    decision = model.decide(_session(), "hello")
    assert decision.kind == "final"
    assert decision.assistant_message == "hi from openai"
    meta = model.last_call_meta()
    assert meta["provider"] == "openai"
    assert meta["api_family"] == "openai_responses"
    assert meta["model_name"] == "gpt-5-mini"
    assert meta["request_tokens"] == 10
    assert meta["response_tokens"] == 2
    assert meta["reasoning_tokens"] == 1


def test_returns_tool_decision() -> None:
    model = OpenAIResponsesModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(
            _response_payload(
                [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "write_file",
                        "arguments": json.dumps({"path": "a.txt", "content": "x"}),
                    }
                ]
            )
        ),
    )
    decision = model.decide(_session(), "write")
    assert decision.kind == "tool"
    assert decision.tool_name == "write_file"


def test_request_body_includes_user_input_when_session_empty() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json=_response_payload(
                [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ]
            ),
        )

    model = OpenAIResponsesModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        reasoning_effort="medium",
        transport=httpx.MockTransport(handler),
    )
    empty = Session(
        id="ses_empty",
        goal="smoke",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[],
    )
    model.decide(empty, "hello smoke")
    assert captured["input"] == [{"role": "user", "content": "hello smoke"}]
    assert captured["reasoning"] == {"effort": "medium"}
    assert isinstance(captured.get("instructions"), str)
