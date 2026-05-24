"""Tests for the Phase 2.2 prompt composition layer."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.core.models import Message, Session
from harnesslab.core.prompt import (
    DEFAULT_STATIC_BLOCKS,
    ComposedPrompt,
    PromptBlock,
    PromptComposer,
    load_default_static_blocks,
)


def _session_with_messages() -> Session:
    s = Session(id="ses_test", goal="probe", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    s.messages.append(
        Message(
            id="msg_u",
            role="user",
            content="hello",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_test",
        )
    )
    s.messages.append(
        Message(
            id="msg_a",
            role="assistant",
            content="hi back",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            session_id="ses_test",
        )
    )
    return s


# ---------- static block loader ----------


def test_default_static_blocks_load_in_order_and_strip_prefix() -> None:
    blocks = load_default_static_blocks()
    names = [b.name for b in blocks]
    # MVP contract: these five blocks ship in this exact order.
    assert names == ["identity", "harness", "safety", "style", "engineering"]
    for b in blocks:
        assert b.role == "system"
        assert b.origin.startswith("static:")
        assert b.content  # non-empty


def test_default_static_blocks_module_attribute_is_cached() -> None:
    assert DEFAULT_STATIC_BLOCKS is not None
    assert [b.name for b in DEFAULT_STATIC_BLOCKS] == [
        b.name for b in load_default_static_blocks()
    ]


def test_identity_block_holds_model_name_placeholder() -> None:
    identity = next(b for b in DEFAULT_STATIC_BLOCKS if b.name == "identity")
    assert "${model_name}" in identity.content


# ---------- composer assembly ----------


def test_build_produces_static_blocks_then_conversation() -> None:
    composer = PromptComposer()
    composed = composer.build(_session_with_messages())

    names = [b.name for b in composed.blocks]
    # Static blocks first, then one conversation block per message.
    assert names[:5] == ["identity", "harness", "safety", "style", "engineering"]
    assert names[5:] == ["conversation", "conversation"]

    last_two = composed.blocks[-2:]
    assert last_two[0].role == "user"
    assert last_two[0].content == "hello"
    assert last_two[0].origin == "session:msg_u"
    assert last_two[1].role == "assistant"
    assert last_two[1].content == "hi back"


def test_build_substitutes_template_variables() -> None:
    composer = PromptComposer()
    composed = composer.build(
        _session_with_messages(),
        variables={"model_name": "deepseek-v4-flash"},
    )
    identity_text = composed.blocks[0].content
    assert "deepseek-v4-flash" in identity_text
    assert "${model_name}" not in identity_text


def test_build_leaves_unknown_placeholders_untouched() -> None:
    """``safe_substitute`` keeps unmatched ``${var}`` so a missing
    variable degrades gracefully instead of crashing the loop."""
    custom = [
        PromptBlock(
            name="custom",
            content="hello ${unknown_var} world",
            origin="test:inline",
        )
    ]
    composer = PromptComposer(static_blocks=custom)
    composed = composer.build(_session_with_messages(), variables={"x": "y"})
    assert composed.blocks[0].content == "hello ${unknown_var} world"


def test_build_appends_dynamic_blocks_between_static_and_conversation() -> None:
    composer = PromptComposer()
    env_block = PromptBlock(name="env", content="cwd=/tmp", origin="dynamic:env")
    composed = composer.build(_session_with_messages(), dynamic_blocks=[env_block])

    names = [b.name for b in composed.blocks]
    assert names == [
        "identity",
        "harness",
        "safety",
        "style",
        "engineering",
        "env",
        "conversation",
        "conversation",
    ]


def test_custom_static_blocks_replace_defaults() -> None:
    composer = PromptComposer(
        static_blocks=[
            PromptBlock(name="only_one", content="solo system prompt", origin="test:inline")
        ]
    )
    composed = composer.build(_session_with_messages())
    names = [b.name for b in composed.blocks]
    assert names == ["only_one", "conversation", "conversation"]


# ---------- serialization ----------


def test_as_text_joins_blocks_with_blank_lines() -> None:
    composer = PromptComposer(
        static_blocks=[
            PromptBlock(name="a", content="first", origin="test:a"),
            PromptBlock(name="b", content="second", origin="test:b"),
        ]
    )
    composed = composer.build(
        Session(id="s", goal="g", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    )
    assert composed.as_text() == "first\n\nsecond"


def test_as_openai_messages_collapses_system_blocks() -> None:
    composer = PromptComposer(
        static_blocks=[
            PromptBlock(name="a", content="aa", origin="test:a"),
            PromptBlock(name="b", content="bb", origin="test:b"),
        ]
    )
    composed = composer.build(_session_with_messages())
    msgs = composed.as_openai_messages()

    assert msgs[0] == {"role": "system", "content": "aa\n\nbb"}
    assert msgs[1] == {"role": "user", "content": "hello"}
    assert msgs[2] == {"role": "assistant", "content": "hi back"}
    assert len(msgs) == 3


def test_as_openai_messages_serializes_tool_turns() -> None:
    composed = ComposedPrompt(
        blocks=[
            PromptBlock(name="u", content="run it", origin="s:1", role="user"),
            PromptBlock(
                name="a",
                content="",
                origin="s:2",
                role="assistant",
                tool_calls=[
                    {
                        "id": "tool_abc",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"a.txt"}',
                        },
                    }
                ],
            ),
            PromptBlock(
                name="t",
                content="ok",
                origin="s:3",
                role="tool",
                tool_call_id="tool_abc",
            ),
        ]
    )
    msgs = composed.as_openai_messages()
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"][0]["id"] == "tool_abc"
    assert msgs[2] == {"role": "tool", "tool_call_id": "tool_abc", "content": "ok"}


def test_as_openai_messages_skips_orphan_tool_blocks() -> None:
    composed = ComposedPrompt(
        blocks=[
            PromptBlock(name="u", content="hi", origin="s:1", role="user"),
            PromptBlock(
                name="t",
                content="legacy orphan",
                origin="s:2",
                role="tool",
                tool_call_id="tool_old",
            ),
        ]
    )
    msgs = composed.as_openai_messages()
    assert msgs == [{"role": "user", "content": "hi"}]


def test_as_openai_messages_keeps_system_when_no_conversation() -> None:
    composer = PromptComposer(
        static_blocks=[PromptBlock(name="sys", content="be helpful", origin="test:s")]
    )
    composed = composer.build(
        Session(id="s", goal="g", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    )
    msgs = composed.as_openai_messages()
    assert msgs == [{"role": "system", "content": "be helpful"}]


def test_snapshot_reports_per_block_metadata() -> None:
    composer = PromptComposer(
        static_blocks=[
            PromptBlock(name="a", content="hello", origin="test:a"),
        ]
    )
    composed = composer.build(_session_with_messages())
    snapshot = composed.snapshot()
    assert snapshot[0] == {
        "name": "a",
        "role": "system",
        "origin": "test:a",
        "char_count": 5,
    }
    user_record = snapshot[1]
    assert user_record["name"] == "conversation"
    assert user_record["role"] == "user"
    assert user_record["origin"] == "session:msg_u"
    assert user_record["char_count"] == len("hello")


# ---------- ComposedPrompt invariants ----------


def test_composed_prompt_is_empty_for_empty_input() -> None:
    composed = ComposedPrompt()
    assert composed.as_text() == ""
    assert composed.as_openai_messages() == []
    assert composed.snapshot() == []
