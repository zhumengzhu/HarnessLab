"""Tests for OpenAI Responses transform (Post-MVP P4)."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.core.models import Message, Session
from harnesslab.core.prompt import PromptComposer
from harnesslab.providers.catalog import CatalogEntry
from harnesslab.providers.transforms.openai_responses import (
    parse_response,
    replay_policy,
    serialize_request,
)


def _entry() -> CatalogEntry:
    return CatalogEntry(
        model_id="gpt-5-mini",
        provider="openai",
        api_family="openai_responses",
        context_window=128_000,
        thinking_default="medium",
        reasoning_support="native",
    )


def _session(*messages: Message) -> Session:
    return Session(
        id="ses_x",
        goal="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=list(messages),
    )


def test_serialize_splits_instructions_and_input() -> None:
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
    wire = serialize_request(composed, session, _entry())
    assert isinstance(wire["instructions"], str)
    assert "HarnessLab" in wire["instructions"]
    assert wire["input"][-1] == {"role": "user", "content": "hello"}


def test_serialize_tool_loop_as_function_call_output() -> None:
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
    wire = serialize_request(composed, session, _entry())
    assert wire["input"][-1] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "matches",
    }


def test_serialize_replays_reasoning_items_in_open_tool_loop() -> None:
    reasoning_item = {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [{"type": "summary_text", "text": "plan"}],
    }
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
            provider_extra={"reasoning_items": [reasoning_item]},
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
    wire = serialize_request(composed, session, _entry())
    types = [item.get("type") for item in wire["input"]]
    assert types.index("reasoning") < types.index("function_call")


def test_parse_response_final_with_reasoning() -> None:
    turn = parse_response(
        {
            "output": [
                {
                    "type": "reasoning",
                    "id": "rs_1",
                    "content": [{"type": "reasoning_text", "text": "hidden"}],
                    "summary": [],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "done"}],
                },
            ]
        },
        _entry(),
    )
    assert turn.decision.kind == "final"
    assert turn.decision.assistant_message == "done"
    assert turn.reasoning_text == "hidden"
    assert turn.provider_extra == {
        "reasoning_items": [
            {
                "type": "reasoning",
                "id": "rs_1",
                "content": [{"type": "reasoning_text", "text": "hidden"}],
                "summary": [],
            }
        ]
    }


def test_parse_response_function_call() -> None:
    turn = parse_response(
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "grep",
                    "arguments": '{"pattern":"foo"}',
                }
            ]
        },
        _entry(),
    )
    assert turn.decision.kind == "tool"
    assert turn.decision.tool_name == "grep"
    assert turn.decision.tool_args == {"pattern": "foo"}


def test_replay_policy_includes_reasoning_in_tool_loop() -> None:
    session = _session(
        Message(
            id="msg_t",
            role="tool",
            content="x",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        )
    )
    assert replay_policy(session, _entry()).include_reasoning_in_tool_loop is True
