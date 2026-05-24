"""Prompt block data model.

Each ``PromptBlock`` is a labeled chunk of prompt text with an explicit
origin so traces and the future ``harnesslab context`` inspector can
attribute tokens back to the file (or runtime source) that produced
them. Blocks are immutable; the composer assembles a fresh
:class:`ComposedPrompt` per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PromptRole = Literal["system", "user", "assistant", "tool"]


def _assistant_tool_call_ids(tool_calls: list[dict[str, Any]] | None) -> set[str]:
    if not tool_calls:
        return set()
    ids: set[str] = set()
    for tc in tool_calls:
        if isinstance(tc, dict):
            tc_id = tc.get("id")
            if isinstance(tc_id, str):
                ids.add(tc_id)
    return ids


def _openai_message_from_block(block: PromptBlock) -> dict[str, Any]:
    if block.role == "assistant" and block.tool_calls:
        payload: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": block.tool_calls,
            "content": block.content or None,
        }
        return payload
    if block.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": block.tool_call_id or "",
            "content": block.content,
        }
    return {"role": block.role, "content": block.content}


def _should_emit_conversation_block(
    block: PromptBlock,
    messages: list[dict[str, Any]],
) -> bool:
    """Skip legacy tool messages that lack a preceding assistant tool_calls."""

    if block.role != "tool":
        return True
    if not block.tool_call_id:
        return False
    if not messages:
        return False
    prev = messages[-1]
    if prev.get("role") != "assistant":
        return False
    tool_calls = prev.get("tool_calls")
    if not isinstance(tool_calls, list):
        return False
    return block.tool_call_id in _assistant_tool_call_ids(tool_calls)


@dataclass(frozen=True)
class PromptBlock:
    """One labeled prompt fragment.

    Attributes:
        name: short identifier (``identity``, ``harness``, ``env``,
            ``agents_md``, ``tool_guide``, ``conversation`` …).
        content: the rendered text.
        origin: where the block came from. ``static:01_harness.md`` for
            packaged ``.md`` files, ``dynamic:env`` for runtime-built
            blocks, ``session:<msg_id>`` for conversation messages.
        role: OpenAI/Anthropic chat role this block maps to when
            serialized. Static blocks default to ``system``; conversation
            blocks carry the message role.
    """

    name: str
    content: str
    origin: str
    role: PromptRole = "system"
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ComposedPrompt:
    """The fully assembled prompt for one model call.

    Carries the blocks in order plus convenience accessors for the two
    shapes downstream code needs: a flat text dump (for SimpleModel and
    debugging) and an OpenAI-style messages array (for DeepSeekModel
    and other chat-completion adapters).
    """

    blocks: list[PromptBlock] = field(default_factory=list)

    def as_text(self) -> str:
        """Concatenate every block in order, separated by blank lines."""

        return "\n\n".join(b.content for b in self.blocks if b.content)

    def as_openai_messages(self) -> list[dict[str, Any]]:
        """Group consecutive ``system`` blocks into a single system
        message, then append non-system blocks in order.

        Collapsing the system blocks matches how OpenAI / DeepSeek
        chat completions treat the system slot: one (long) message
        rather than many short ones. Conversation blocks keep their
        original roles so tool/assistant/user turns round-trip
        unchanged.
        """

        messages: list[dict[str, Any]] = []
        system_parts: list[str] = []

        for block in self.blocks:
            if block.role == "system":
                if block.content:
                    system_parts.append(block.content)
                continue
            if system_parts:
                messages.append(
                    {"role": "system", "content": "\n\n".join(system_parts)}
                )
                system_parts = []
            if not _should_emit_conversation_block(block, messages):
                continue
            messages.append(_openai_message_from_block(block))

        if system_parts:
            # No non-system block appeared; emit the system message at
            # the front so the model still sees the system prompt.
            messages.insert(
                0, {"role": "system", "content": "\n\n".join(system_parts)}
            )

        return messages

    def snapshot(self) -> list[dict[str, object]]:
        """Per-block metadata for ``harnesslab context`` (Phase 2.6).

        Returns one record per block with ``name``, ``role``, ``origin``,
        and ``char_count``. Token estimation is intentionally left to
        the caller — the composer should not depend on a tokenizer.
        """

        return [
            {
                "name": b.name,
                "role": b.role,
                "origin": b.origin,
                "char_count": len(b.content),
            }
            for b in self.blocks
        ]
