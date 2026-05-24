"""Unit tests for GeminiModel provider adapter (Post-MVP P5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from harnesslab.core.models import Message, Session
from harnesslab.providers.gemini import GeminiModel
from harnesslab.providers.transports.google_genai import GoogleGenAITransport


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


def _gemini_response(text: str, *, usage: dict | None = None) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": text}],
                }
            }
        ],
        "usageMetadata": usage
        or {"promptTokenCount": 8, "candidatesTokenCount": 3, "totalTokenCount": 11},
    }


class _FakeModels:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.last_body: dict[str, Any] | None = None

    def generate_content(
        self,
        *,
        model: str,
        contents: Any,
        config: Any | None = None,
    ) -> Any:
        self.last_body = {"model": model, "contents": contents, "config": config}

        class _Response:
            def model_dump(self, *, mode: str = "json") -> dict[str, Any]:
                return self._payload

        resp = _Response()
        resp._payload = self._payload
        return resp


class _FakeClient:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models


def _transport(payload: dict[str, Any]) -> GoogleGenAITransport:
    fake = _FakeModels(payload)
    return GoogleGenAITransport(api_key="x", client=_FakeClient(fake))  # type: ignore[arg-type]


def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GeminiModel(tool_specs_provider=lambda: [])


def test_returns_final_decision() -> None:
    transport = _transport(_gemini_response("hi from gemini"))
    model = GeminiModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        genai_transport=transport,
    )
    decision = model.decide(_session(), "hello")
    assert decision.kind == "final"
    assert decision.assistant_message == "hi from gemini"
    meta = model.last_call_meta()
    assert meta["provider"] == "google"
    assert meta["api_family"] == "google_generate_content"
    assert meta["model_name"] == "gemini-2.5-flash"
    assert meta["request_tokens"] == 8
    assert meta["total_tokens"] == 11


def test_budget_schema_sets_thinking_budget() -> None:
    transport = _transport(_gemini_response("ok"))
    model = GeminiModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        model_name="gemini-2.5-flash",
        thinking_budget=1024,
        genai_transport=transport,
    )
    model.decide(_session(), "hello")
    assert model.last_call_meta()["thinking_schema"] == "budget"


def test_level_schema_sets_thinking_level() -> None:
    transport = _transport(_gemini_response("ok"))
    model = GeminiModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        model_name="gemini-3-flash-preview",
        thinking_level="high",
        genai_transport=transport,
    )
    model.decide(_session(), "hello")
    assert model.last_call_meta()["thinking_schema"] == "level"


def test_eval_style_mock_assistant_reply() -> None:
    """Eval-style smoke: deterministic mock, no network."""

    transport = _transport(_gemini_response("The answer is 42."))
    model = GeminiModel(tool_specs_provider=lambda: [], api_key="x", genai_transport=transport)
    decision = model.decide(_session(), "What is the meaning of life?")
    assert decision.kind == "final"
    assert "42" in (decision.assistant_message or "")
