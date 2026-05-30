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


def test_serialize_replays_all_tool_assistants_in_multi_turn_history() -> None:
    thought_one = [{"text": "turn one plan", "thought": True, "thought_signature": "sig_1"}]
    thought_two = [{"text": "turn two plan", "thought": True, "thought_signature": "sig_2"}]
    session = _session(
        Message(
            id="msg_u1",
            role="user",
            content="run tool",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
        Message(
            id="msg_a1",
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
            provider_extra={"thought_parts": thought_one},
        ),
        Message(
            id="msg_t1",
            role="tool",
            content="matches",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        ),
        Message(
            id="msg_a2",
            role="assistant",
            content="done",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
        Message(
            id="msg_u2",
            role="user",
            content="again",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
        Message(
            id="msg_a3",
            role="assistant",
            content="",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_calls=[
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'},
                }
            ],
            provider_extra={"thought_parts": thought_two},
        ),
        Message(
            id="msg_t2",
            role="tool",
            content="file",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_2",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_request(composed, session, _level_entry())
    tool_turns = [
        turn
        for turn in wire["contents"]
        if turn.get("role") == "model"
        and isinstance(turn.get("parts"), list)
        and any(
            isinstance(part, dict) and ("functionCall" in part or "function_call" in part)
            for part in turn["parts"]
        )
    ]
    assert len(tool_turns) == 2
    assert tool_turns[0]["parts"][0]["thought"] is True
    assert tool_turns[0]["parts"][0]["text"] == "turn one plan"
    assert tool_turns[1]["parts"][0]["text"] == "turn two plan"


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


def test_replay_policy_none_for_reasoning_support_none() -> None:
    entry = CatalogEntry(
        model_id="gemini-2.5-flash",
        provider="google",
        api_family="google_generate_content",
        context_window=1_048_576,
        thinking_default="disabled",
        reasoning_support="none",
    )
    session = _session(
        Message(
            id="msg_t",
            role="tool",
            content="ok",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        )
    )
    assert replay_policy(session, entry).include_reasoning_in_tool_loop is False


def test_serialize_replays_thought_from_reasoning_text_fallback() -> None:
    session = _session(
        Message(
            id="msg_u",
            role="user",
            content="grep",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
        Message(
            id="msg_a",
            role="assistant",
            content="",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            reasoning_text="fallback gemini thought",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "grep", "arguments": "{}"},
                }
            ],
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
    composed = PromptComposer().build(session)
    wire = serialize_request(composed, session, _level_entry())
    model_turn = next(m for m in wire["contents"] if m["role"] == "model")
    assert model_turn["parts"][0]["thought"] is True
    assert model_turn["parts"][0]["text"] == "fallback gemini thought"


def test_replay_policy_after_closed_loop_includes_persisted_thoughts() -> None:
    session = _session(
        Message(
            id="msg_a1",
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
                "thought_parts": [{"text": "earlier", "thought": True, "thought_signature": "s"}]
            },
        ),
        Message(
            id="msg_t1",
            role="tool",
            content="ok",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        ),
        Message(
            id="msg_u2",
            role="user",
            content="continue",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
    )
    assert replay_policy(session, _level_entry()).include_reasoning_in_tool_loop is True
