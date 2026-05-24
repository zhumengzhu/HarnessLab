"""Tests for Google Gemini generateContent transform (Post-MVP P5)."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.core.models import Message, Session
from harnesslab.core.prompt import PromptComposer
from harnesslab.providers.catalog import CatalogEntry
from harnesslab.providers.transforms.google_generate_content import (
    parse_response,
    replay_policy,
    serialize_request,
)


def _budget_entry() -> CatalogEntry:
    return CatalogEntry(
        model_id="gemini-2.5-flash",
        provider="google",
        api_family="google_generate_content",
        context_window=1_048_576,
        thinking_default="dynamic",
        reasoning_support="native",
        thinking_schema="budget",
    )


def _level_entry() -> CatalogEntry:
    return CatalogEntry(
        model_id="gemini-3-flash-preview",
        provider="google",
        api_family="google_generate_content",
        context_window=1_048_576,
        thinking_default="high",
        reasoning_support="native",
        thinking_schema="level",
    )


def _session(*messages: Message) -> Session:
    return Session(
        id="ses_x",
        goal="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=list(messages),
    )


def test_serialize_splits_system_and_contents() -> None:
    session = _session(
        Message(
            id="msg_u",
            role="user",
            content="hello",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        )
    )
    composed = PromptComposer().build(session)
    wire = serialize_request(composed, session, _budget_entry())
    assert isinstance(wire["system_instruction"], dict)
    assert wire["contents"][-1]["role"] == "user"
    assert wire["contents"][-1]["parts"][0]["text"] == "hello"


def test_serialize_tool_loop_as_function_response() -> None:
    session = _session(
        Message(
            id="msg_a",
            role="assistant",
            content="",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "grep", "arguments": '{"pattern":"x"}'},
                }
            ],
        ),
        Message(
            id="msg_t",
            role="tool",
            content="matches",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_request(composed, session, _budget_entry())
    last = wire["contents"][-1]
    assert last["role"] == "user"
    assert last["parts"][0]["functionResponse"]["response"]["result"] == "matches"


def test_replay_policy_includes_thoughts_in_tool_loop() -> None:
    session = _session(
        Message(
            id="msg_a",
            role="assistant",
            content="",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "grep", "arguments": "{}"},
                }
            ],
            provider_extra={
                "thought_parts": [{"text": "plan", "thought": True, "thought_signature": "abc"}]
            },
        ),
        Message(
            id="msg_t",
            role="tool",
            content="ok",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        ),
    )
    policy = replay_policy(session, _level_entry())
    assert policy.include_reasoning_in_tool_loop is True
    composed = PromptComposer().build(session)
    wire = serialize_request(composed, session, _level_entry())
    model_turn = next(m for m in wire["contents"] if m["role"] == "model")
    assert model_turn["parts"][0]["thought"] is True


def test_parse_response_text() -> None:
    payload = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": "hello gemini"}],
                }
            }
        ]
    }
    turn = parse_response(payload, _budget_entry())
    assert turn.decision.kind == "final"
    assert turn.decision.assistant_message == "hello gemini"


def test_parse_response_thought_and_tool() -> None:
    payload = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"text": "reason", "thought": True},
                        {"functionCall": {"name": "read_file", "args": {"path": "a.txt"}}},
                    ],
                }
            }
        ]
    }
    turn = parse_response(payload, _budget_entry())
    assert turn.decision.kind == "tool"
    assert turn.decision.tool_name == "read_file"
    assert turn.reasoning_text == "reason"
    assert turn.provider_extra is not None
    assert "thought_parts" in turn.provider_extra
