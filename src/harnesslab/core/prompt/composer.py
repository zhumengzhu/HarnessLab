"""Compose ``PromptBlock`` lists into a ``ComposedPrompt``.

The composer's first responsibility is loading the packaged static
blocks (``blocks/*.md``), substituting their template variables
(``${model_name}``…), and pasting the session's conversation messages
on the end. Dynamic blocks (``env``, ``agents_md``, ``tool_guide``)
are passed in by the caller so the composer never has to reach for
``os`` / filesystem / git state itself — that wiring lands in
Phase 2.2 commit 2 where DeepSeek starts consuming the composer.
"""

from __future__ import annotations

import importlib.resources
from dataclasses import replace
from string import Template

from harnesslab.core.models import Session
from harnesslab.core.prompt.block import ComposedPrompt, PromptBlock

_BLOCKS_PACKAGE = "harnesslab.core.prompt.blocks"


def _strip_numeric_prefix(stem: str) -> str:
    """``00_identity`` → ``identity``; ``identity`` → ``identity``."""

    head, sep, tail = stem.partition("_")
    if sep and head.isdigit() and tail:
        return tail
    return stem


def _substitute(block: PromptBlock, variables: dict[str, str]) -> PromptBlock:
    if not variables or "$" not in block.content:
        return block
    rendered = Template(block.content).safe_substitute(variables)
    if rendered == block.content:
        return block
    return replace(block, content=rendered)


def load_default_static_blocks() -> list[PromptBlock]:
    """Read every ``NN_<name>.md`` file under the blocks package.

    Files are loaded in filename order so the numeric prefix controls
    composition order (``00_identity.md`` → ``04_engineering.md``).
    The ``NN_`` prefix is stripped from the resulting block name.
    Empty files are skipped.
    """

    blocks: list[PromptBlock] = []
    package = importlib.resources.files(_BLOCKS_PACKAGE)
    entries = sorted(
        (p for p in package.iterdir() if p.name.endswith(".md")),
        key=lambda p: p.name,
    )
    for entry in entries:
        content = entry.read_text(encoding="utf-8").strip()
        if not content:
            continue
        blocks.append(
            PromptBlock(
                name=_strip_numeric_prefix(entry.name[: -len(".md")]),
                content=content,
                origin=f"static:{entry.name}",
                role="system",
            )
        )
    return blocks


# Computed once at import time. Static blocks are immutable, so it is
# safe to share the list across composer instances; the composer copies
# (and template-substitutes) before publishing them.
DEFAULT_STATIC_BLOCKS: list[PromptBlock] = load_default_static_blocks()


class PromptComposer:
    """Assemble a per-call prompt from static + dynamic + conversation blocks.

    Composition order:

    1. Static blocks (packaged ``.md`` files, after variable substitution).
    2. Caller-supplied dynamic blocks, in the order they were passed.
    3. Conversation messages from ``session.messages``, one block each.

    The composer never reads ``os`` / git / filesystem state itself;
    the env / agents_md / tool_guide blocks are produced by adapters
    or CLI surfaces with the right context and threaded in via
    ``dynamic_blocks``.
    """

    def __init__(self, static_blocks: list[PromptBlock] | None = None) -> None:
        # Defensive copy so the caller can mutate their list later
        # without surprising us.
        self._static_blocks: list[PromptBlock] = list(
            static_blocks if static_blocks is not None else DEFAULT_STATIC_BLOCKS
        )

    def build(
        self,
        session: Session,
        *,
        dynamic_blocks: list[PromptBlock] | None = None,
        variables: dict[str, str] | None = None,
    ) -> ComposedPrompt:
        variables = dict(variables or {})
        blocks: list[PromptBlock] = [
            _substitute(b, variables) for b in self._static_blocks
        ]
        if dynamic_blocks:
            blocks.extend(_substitute(b, variables) for b in dynamic_blocks)
        for msg in session.messages:
            blocks.append(
                PromptBlock(
                    name="conversation",
                    content=msg.content,
                    origin=f"session:{msg.id}",
                    role=msg.role,
                    tool_call_id=msg.tool_call_id,
                    tool_calls=msg.tool_calls,
                )
            )
        return ComposedPrompt(blocks=blocks)


