"""Tests for OpenAI Chat Completions transform hooks (Post-MVP P1).

Parse edge cases shared with DeepSeek (invalid JSON, empty choices) live in
``test_deepseek_provider.py`` as adapter integration smoke tests. This module
owns serialize/replay policy and reasoning-specific parse coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.core.models import Message, Session
from harnesslab.core.prompt import ComposedPrompt, PromptBlock, PromptComposer
from harnesslab.providers.catalog import CatalogEntry
from harnesslab.providers.transforms.openai_chat import (
    parse_response,
    replay_policy,
    serialize_messages,
)


def _entry() -> CatalogEntry:
    return CatalogEntry(
        model_id="deepseek-v4-flash",
        provider="deepseek",
        api_family="openai_chat",
        context_window=128_000,
        thinking_default="disabled",
        reasoning_support="native",
    )


def _session(*messages: Message) -> Session:
    return Session(
        id="ses_x",
        goal="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=list(messages),
    )


def test_serialize_matches_composed_openai_messages_without_reasoning() -> None:
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
    assert wire == composed.as_openai_messages()


def test_replay_policy_includes_reasoning_when_last_message_is_tool() -> None:
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
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
            reasoning_text="chain-of-thought",
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
    policy = replay_policy(session, _entry())
    assert policy.include_reasoning_in_tool_loop is True


def test_serialize_injects_reasoning_content_in_open_tool_loop() -> None:
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
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
            reasoning_text="think step",
        ),
        Message(
            id="msg_t",
            role="tool",
            content="file contents",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_messages(composed, session, _entry())
    assistant_msgs = [m for m in wire if m.get("role") == "assistant" and m.get("tool_calls")]
    assert assistant_msgs
    assert assistant_msgs[-1]["reasoning_content"] == "think step"


def test_serialize_replays_reasoning_on_new_user_turn_after_tool_history() -> None:
    """DeepSeek rejects requests when historical tool-loop assistants omit reasoning."""
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
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
            reasoning_text="turn one thought",
        ),
        Message(
            id="msg_t1",
            role="tool",
            content="file contents",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
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
            content="continue",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_messages(composed, session, _entry())
    tool_assistants = [m for m in wire if m.get("role") == "assistant" and m.get("tool_calls")]
    assert len(tool_assistants) == 1
    assert tool_assistants[0]["reasoning_content"] == "turn one thought"
    assert replay_policy(session, _entry()).include_reasoning_in_tool_loop is True


def test_serialize_replays_reasoning_on_non_tool_assistant() -> None:
    """Mid-loop assistant/plan rows with thinking must replay reasoning_content."""
    session = _session(
        Message(
            id="msg_u",
            role="user",
            content="research",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        ),
        Message(
            id="msg_a1",
            role="assistant",
            content="Planning next step…",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            reasoning_text="plan before tool",
        ),
        Message(
            id="msg_a2",
            role="assistant",
            content="",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": "{}"},
                }
            ],
            reasoning_text="tool step thought",
        ),
        Message(
            id="msg_t1",
            role="tool",
            content="results",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_messages(composed, session, _entry())
    assistants = [m for m in wire if m.get("role") == "assistant"]
    assert assistants[0]["reasoning_content"] == "plan before tool"
    assert assistants[1]["reasoning_content"] == "tool step thought"


def test_serialize_replays_empty_reasoning_for_tool_assistant_without_thinking() -> None:
    """Tool rows in thinking mode must send reasoning_content even when empty."""
    session = _session(
        Message(
            id="msg_u",
            role="user",
            content="research",
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
                    "function": {"name": "web_search", "arguments": "{}"},
                }
            ],
            reasoning_text="",
        ),
        Message(
            id="msg_t1",
            role="tool",
            content="results",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_messages(composed, session, _entry())
    tool_assistants = [m for m in wire if m.get("role") == "assistant" and m.get("tool_calls")]
    assert len(tool_assistants) == 1
    assert tool_assistants[0]["reasoning_content"] == ""


def test_serialize_replays_empty_reasoning_when_tool_assistant_reasoning_null() -> None:
    """Legacy rows with NULL reasoning still replay an empty field on the wire."""
    session = _session(
        Message(
            id="msg_u",
            role="user",
            content="research",
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
                    "function": {"name": "fetch_url", "arguments": "{}"},
                }
            ],
            reasoning_text=None,
        ),
        Message(
            id="msg_t1",
            role="tool",
            content="results",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
            tool_call_id="call_1",
        ),
    )
    composed = PromptComposer().build(session)
    wire = serialize_messages(composed, session, _entry())
    tool_assistants = [m for m in wire if m.get("role") == "assistant" and m.get("tool_calls")]
    assert tool_assistants[0]["reasoning_content"] == ""


def test_parse_response_final_with_reasoning() -> None:
    turn = parse_response(
        {
            "choices": [
                {
                    "message": {
                        "content": "done",
                        "reasoning_content": "  hidden  ",
                    }
                }
            ]
        },
        _entry(),
    )
    assert turn.decision.kind == "final"
    assert turn.decision.assistant_message == "done"
    assert turn.reasoning_text == "hidden"


def test_parse_response_reads_reasoning_alias_field() -> None:
    turn = parse_response(
        {
            "choices": [
                {
                    "message": {
                        "content": "done",
                        "reasoning": "alias path",
                    }
                }
            ]
        },
        _entry(),
    )
    assert turn.reasoning_text == "alias path"


def test_parse_response_tool_with_reasoning() -> None:
    turn = parse_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "grep",
                                    "arguments": '{"pattern":"foo"}',
                                }
                            }
                        ],
                        "reasoning_content": "need grep",
                    }
                }
            ]
        },
        _entry(),
    )
    assert turn.decision.kind == "tool"
    assert turn.decision.tool_name == "grep"
    assert turn.decision.tool_args == {"pattern": "foo"}
    assert turn.reasoning_text == "need grep"


def test_replay_policy_none_for_reasoning_support_none() -> None:
    entry = CatalogEntry(
        model_id="plain",
        provider="mock",
        api_family="openai_chat",
        context_window=4096,
        thinking_default="disabled",
        reasoning_support="none",
    )
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
    assert replay_policy(session, entry).include_reasoning_in_tool_loop is False


def test_composed_prompt_direct_equivalence_for_static_blocks() -> None:
    composed = ComposedPrompt(
        blocks=[
            PromptBlock(name="identity", content="You are helpful.", origin="static:identity"),
            PromptBlock(
                name="conversation",
                content="hi",
                origin="session:msg_u",
                role="user",
            ),
        ]
    )
    session = _session(
        Message(
            id="msg_u",
            role="user",
            content="hi",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_x",
        )
    )
    assert serialize_messages(composed, session, _entry()) == composed.as_openai_messages()
