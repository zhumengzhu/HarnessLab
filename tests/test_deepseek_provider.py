"""Unit tests for DeepSeekModel provider adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from harnesslab.core.models import Message, Session
from harnesslab.providers.deepseek import DeepSeekModel, tool_specs_from_registry


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


def _transport(payload: dict, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=payload)

    return httpx.MockTransport(handler)


def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError):
        DeepSeekModel(tool_specs_provider=lambda: [])


def test_returns_final_decision_when_no_tool_calls() -> None:
    """Assistant text without tool_calls is the OpenAI/DeepSeek
    convention for "I'm done"; the loop treats that as a terminal
    decision (``kind="final"``)."""
    payload = {
        "choices": [{"message": {"content": "hi from deepseek"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }
    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(payload),
    )
    decision = model.decide(_session(), "hello")
    assert decision.kind == "final"
    assert decision.assistant_message == "hi from deepseek"
    assert model.last_call_meta() == {
        "provider": "deepseek",
        "model_name": "deepseek-chat",
        "request_tokens": 10,
        "response_tokens": 2,
        "total_tokens": 12,
    }


def test_returns_tool_decision() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps({"path": "a.txt", "content": "x"}),
                            }
                        }
                    ]
                }
            }
        ],
        "usage": {},
    }
    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(payload),
    )
    decision = model.decide(_session(), "write")
    assert decision.kind == "tool"
    assert decision.tool_name == "write_file"
    assert decision.tool_args == {"path": "a.txt", "content": "x"}


def test_invalid_tool_call_json_falls_back_to_final() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "write_file", "arguments": "{not json"}}
                    ]
                }
            }
        ]
    }
    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport(payload),
    )
    decision = model.decide(_session(), "write")
    assert decision.kind == "final"
    assert "invalid JSON args" in (decision.assistant_message or "")


def test_http_error_falls_back_to_final() -> None:
    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=_transport({"error": "bad"}, status_code=500),
    )
    decision = model.decide(_session(), "hello")
    assert decision.kind == "final"
    assert "DeepSeek request failed" in (decision.assistant_message or "")
    assert model.last_call_meta() == {
        "provider": "deepseek",
        "model_name": "deepseek-chat",
    }


def test_tool_specs_from_registry_extracts_schema() -> None:
    class FakeTool:
        name = "read_file"
        description = "read one file"
        args_schema = {"type": "object", "required": ["path"]}

    specs = tool_specs_from_registry([FakeTool()])
    assert specs == [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "read one file",
                "parameters": {"type": "object", "required": ["path"]},
            },
        }
    ]


def test_request_body_includes_tools_spec() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    model = DeepSeekModel(
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
        transport=httpx.MockTransport(handler),
    )
    decision = model.decide(_session(), "hello")
    assert decision.kind == "final"
    assert captured["model"] == "deepseek-chat"
    assert captured["tool_choice"] == "auto"
    assert captured["tools"][0]["function"]["name"] == "read_file"


# ----- prompt composer wiring (Phase 2.2 commit 2) -----


def test_request_body_uses_prompt_composer_system_prompt() -> None:
    """The system message must come from the packaged static blocks
    (identity / harness / safety / style / engineering) and have the
    ``${model_name}`` placeholder filled in."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=httpx.MockTransport(handler),
    )
    model.decide(_session(), "hello")

    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    system_text = messages[0]["content"]
    assert "HarnessLab's agent" in system_text
    assert "deepseek-chat" in system_text  # ${model_name} interpolated
    assert "${model_name}" not in system_text
    assert "# Harness" in system_text
    assert "# Safety" in system_text


def test_request_body_appends_dynamic_blocks_from_provider() -> None:
    from harnesslab.core.prompt import PromptBlock

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    env_block = PromptBlock(
        name="env",
        content="# Environment\n\n- cwd: /demo",
        origin="dynamic:env",
    )

    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=httpx.MockTransport(handler),
        dynamic_blocks_provider=lambda _s: [env_block],
    )
    model.decide(_session(), "hi")

    system_text = captured["messages"][0]["content"]
    assert "cwd: /demo" in system_text
    # Dynamic blocks come AFTER static ones in the composer order.
    assert system_text.index("# Harness") < system_text.index("cwd: /demo")


def test_request_body_preserves_session_conversation() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=httpx.MockTransport(handler),
    )
    model.decide(_session(), "hi")

    messages = captured["messages"]
    # One system message + one user message (from _session()'s "hello").
    assert len(messages) == 2
    assert messages[1] == {"role": "user", "content": "hello"}


def test_last_prompt_exposes_block_snapshot() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
        api_key="x",
        transport=httpx.MockTransport(handler),
    )
    assert model.last_prompt() is None
    model.decide(_session(), "hi")
    composed = model.last_prompt()
    assert composed is not None
    snapshot = composed.snapshot()
    names = [r["name"] for r in snapshot]
    # Static blocks land first; the session's single message is appended last.
    assert names[:5] == ["identity", "harness", "safety", "style", "engineering"]
    assert names[-1] == "conversation"
