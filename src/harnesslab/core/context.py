"""Context window observability primitives.

Each ``model_call`` trace event carries a ``ContextSnapshot`` so
operators can see how close a session is to its configured budget
without having to recompute it from raw messages.

Two halves contribute to a snapshot:

* The loop measures the *conversation* side — the tokens that come
  from ``session.messages`` after any pre-call compaction.
* The model adapter optionally fills in the *prompt* side —
  rendered system blocks plus the formatted conversation as it was
  actually sent to the model. Adapters do this by exposing
  ``prompt_tokens_estimate``, ``static_block_tokens``,
  ``dynamic_block_tokens`` and ``prompt_block_names`` from
  ``last_call_meta()``.

The token figures are estimates (see ``compaction.estimate_tokens``)
and intentionally provider-agnostic. The dashboard / context CLI
treats them as the source of truth for "context usage", and the
provider's own ``total_tokens`` (when reported) is recorded
separately so the two can be cross-checked.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from harnesslab.core.compaction import estimate_messages_tokens, estimate_tokens
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import Message


class ContextSnapshot(BaseModel):
    """A point-in-time view of a model call's context budget."""

    conversation_tokens: int = Field(ge=0)
    message_count: int = Field(ge=0)
    limit_tokens: int = Field(ge=1)
    compaction_threshold_tokens: int = Field(ge=1)
    usage_ratio: float = Field(ge=0.0)
    threshold_ratio: float = Field(ge=0.0)

    prompt_tokens_estimate: int | None = Field(default=None, ge=0)
    static_block_tokens: int | None = Field(default=None, ge=0)
    dynamic_block_tokens: int | None = Field(default=None, ge=0)
    prompt_block_names: list[str] | None = None
    context_breakdown_tokens: dict[str, int] | None = None


def make_conversation_snapshot(
    messages: list[Message],
    limits: RuntimeLimits,
) -> ContextSnapshot:
    """Compute the conversation side of a snapshot."""

    conversation_tokens = estimate_messages_tokens(messages)
    limit = max(1, limits.context_window_tokens)
    threshold = max(1, limits.compaction_threshold_tokens)
    return ContextSnapshot(
        conversation_tokens=conversation_tokens,
        message_count=len(messages),
        limit_tokens=limit,
        compaction_threshold_tokens=threshold,
        usage_ratio=round(conversation_tokens / limit, 4),
        threshold_ratio=round(conversation_tokens / threshold, 4),
        context_breakdown_tokens=_conversation_breakdown(messages),
    )


def merge_adapter_breakdown(
    snapshot: ContextSnapshot,
    adapter_meta: dict[str, Any] | None,
) -> ContextSnapshot:
    """Fold adapter-reported prompt-side fields into ``snapshot``.

    Unknown keys are ignored. Negative values are clamped to ``None``
    so we never publish a meaningless ``-1``.
    """

    if not isinstance(adapter_meta, dict):
        return snapshot

    def _int_or_none(value: Any) -> int | None:
        if not isinstance(value, int):
            return None
        return value if value >= 0 else None

    block_names = adapter_meta.get("prompt_block_names")
    if isinstance(block_names, list):
        names: list[str] | None = [str(n) for n in block_names]
    else:
        names = None

    merged_breakdown = dict(snapshot.context_breakdown_tokens or {})
    for key, value in _adapter_breakdown(adapter_meta).items():
        merged_breakdown[key] = merged_breakdown.get(key, 0) + value

    return snapshot.model_copy(
        update={
            "prompt_tokens_estimate": _int_or_none(
                adapter_meta.get("prompt_tokens_estimate")
            ),
            "static_block_tokens": _int_or_none(
                adapter_meta.get("static_block_tokens")
            ),
            "dynamic_block_tokens": _int_or_none(
                adapter_meta.get("dynamic_block_tokens")
            ),
            "prompt_block_names": names,
            "context_breakdown_tokens": merged_breakdown or None,
        }
    )


def _conversation_breakdown(messages: list[Message]) -> dict[str, int]:
    out = {"conversation": 0, "summarized_conversation": 0}
    for msg in messages:
        tokens = estimate_tokens(msg.content)
        if msg.role == "system" and _is_compaction_summary(msg.content):
            out["summarized_conversation"] += tokens
        else:
            out["conversation"] += tokens
    return out


def _adapter_breakdown(adapter_meta: dict[str, Any]) -> dict[str, int]:
    raw = adapter_meta.get("prompt_block_breakdown")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, int):
            continue
        if value < 0:
            continue
        out[key] = value
    return out


def _is_compaction_summary(content: str) -> bool:
    text = content.strip()
    return (
        "<system-reminder>" in text
        and "</system-reminder>" in text
        and "Compacted earlier conversation" in text
    )
