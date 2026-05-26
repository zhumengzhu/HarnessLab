"""Tests for Anthropic Messages transform (Post-MVP P3)."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.core.models import Message, Session
from harnesslab.core.prompt import PromptComposer
from harnesslab.providers.catalog import CatalogEntry
from harnesslab.providers.transforms.anthropic_messages import (
    parse_response,
    replay_policy,
    serialize_messages,
)


def _entry() -> CatalogEntry:
    return CatalogEntry(
        model_id="claude-sonnet-4-6",
        provider="anthropic",
        api_family="anthropic_messages",
        context_window=200_000,
        thinking_default="adaptive",
        reasoning_support="native",
    )


def _session(*messages: Message) -> Session:
    return Session(
        id="ses_x",
        goal="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=list(messages),
    )


def test_serialize_splits_system_and_conversation() -> None:
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
    wire = serialize_messages(composed, session, _entry())
    assert isinstance(wire["system"], str)
    assert "HarnessLab" in wire["system"]
    assert wire["messages"][-1] == {"role": "user", "content": "hello"}


def test_serialize_converts_tool_loop_to_anthropic_blocks() -> None:
    session = _session(
        Message(
            id="msg_u",
            role="user",
            content="run tool",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
        Message(
            id="msg_a",
            role="assistant",
            content="",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_calls=[
                {
                    "id": "toolu_01",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        ),
        Message(
            id="msg_t",
            role="tool",
            content="file contents",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="toolu_01",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_messages(composed, session, _entry())
    assistant = [m for m in wire["messages"] if m["role"] == "assistant"][-1]
    assert assistant["content"][0]["type"] == "tool_use"
    assert assistant["content"][0]["id"] == "toolu_01"
    tool_result_msg = wire["messages"][-1]
    assert tool_result_msg["role"] == "user"
    assert tool_result_msg["content"][0]["type"] == "tool_result"
    assert tool_result_msg["content"][0]["tool_use_id"] == "toolu_01"


def test_replay_policy_includes_thinking_when_last_message_is_tool() -> None:
    session = _session(
        Message(
            id="msg_t",
            role="tool",
            content="ok",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="toolu_01",
        )
    )
    assert replay_policy(session, _entry()).include_reasoning_in_tool_loop is True


def test_serialize_replays_thinking_blocks_in_open_tool_loop() -> None:
    thinking_block = {
        "type": "thinking",
        "thinking": "plan step",
        "signature": "sig_abc",
    }
    session = _session(
        Message(
            id="msg_u",
            role="user",
            content="run grep",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
        Message(
            id="msg_a",
            role="assistant",
            content="",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_calls=[
                {
                    "id": "toolu_01",
                    "type": "function",
                    "function": {"name": "grep", "arguments": '{"pattern":"foo"}'},
                }
            ],
            provider_extra={"thinking_blocks": [thinking_block]},
        ),
        Message(
            id="msg_t",
            role="tool",
            content="matches",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="toolu_01",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_messages(composed, session, _entry())
    assistant = [m for m in wire["messages"] if m["role"] == "assistant"][-1]
    assert assistant["content"][0] == thinking_block
    assert assistant["content"][1]["type"] == "tool_use"


def test_parse_response_final_with_thinking() -> None:
    turn = parse_response(
        {
            "content": [
                {"type": "thinking", "thinking": "hidden", "signature": "sig"},
                {"type": "text", "text": "done"},
            ]
        },
        _entry(),
    )
    assert turn.decision.kind == "final"
    assert turn.decision.assistant_message == "done"
    assert turn.reasoning_text == "hidden"
    assert turn.provider_extra == {
        "thinking_blocks": [{"type": "thinking", "thinking": "hidden", "signature": "sig"}]
    }


def test_serialize_replays_all_tool_assistants_in_multi_turn_history() -> None:
    """Closed tool loop + new user turn must still replay earlier thinking blocks."""

    thinking_one = {
        "type": "thinking",
        "thinking": "turn one plan",
        "signature": "sig_1",
    }
    thinking_two = {
        "type": "thinking",
        "thinking": "turn two plan",
        "signature": "sig_2",
    }
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
                    "id": "toolu_01",
                    "type": "function",
                    "function": {"name": "grep", "arguments": '{"pattern":"foo"}'},
                }
            ],
            provider_extra={"thinking_blocks": [thinking_one]},
        ),
        Message(
            id="msg_t1",
            role="tool",
            content="matches",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="toolu_01",
        ),
        Message(
            id="msg_a2",
            role="assistant",
            content="done after tool",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
        Message(
            id="msg_u2",
            role="user",
            content="run another tool",
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
                    "id": "toolu_02",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'},
                }
            ],
            provider_extra={"thinking_blocks": [thinking_two]},
        ),
        Message(
            id="msg_t2",
            role="tool",
            content="file",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="toolu_02",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_messages(composed, session, _entry())
    tool_assistants = [
        m
        for m in wire["messages"]
        if m.get("role") == "assistant"
        and isinstance(m.get("content"), list)
        and any(b.get("type") == "tool_use" for b in m["content"])
    ]
    assert len(tool_assistants) == 2
    assert tool_assistants[0]["content"][0] == thinking_one
    assert tool_assistants[1]["content"][0] == thinking_two
    assert replay_policy(session, _entry()).include_reasoning_in_tool_loop is True


def test_parse_response_tool_use() -> None:
    turn = parse_response(
        {
            "content": [
                {"type": "thinking", "thinking": "need grep"},
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "grep",
                    "input": {"pattern": "foo"},
                },
            ]
        },
        _entry(),
    )
    assert turn.decision.kind == "tool"
    assert turn.decision.tool_name == "grep"
    assert turn.decision.tool_args == {"pattern": "foo"}
    assert turn.reasoning_text == "need grep"
