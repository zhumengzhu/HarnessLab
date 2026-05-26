"""Context compaction for long-running sessions.

When ``session.messages`` would push the next model call past the
configured threshold, the loop calls :func:`compact_messages` to
replace older messages with a single summary message. If the model
itself reports overflow (via :class:`ModelOverflowError`), the loop
runs an emergency compaction with a much smaller ``keep_last`` and
retries the call once.

Concepts:

- :func:`estimate_tokens` is a heuristic ``len(text) // 4``. It is
  intentionally model-agnostic so the loop can decide *whether* to
  compact without depending on a specific tokenizer. Adapters that
  know better may report their own token counts in trace events.
- :func:`should_compact` answers "do I need to compact before the
  next model call?" given a token budget.
- :func:`compact_messages` performs the compaction: keep the last
  ``keep_last`` messages verbatim, replace the rest with one summary
  ``system`` message whose body is produced by ``summarizer``.
- :class:`ModelOverflowError` is the contract between adapters and
  the loop for "the API rejected this request because the context
  window is too small for what we sent".
- :class:`LiveSummarizer` is an opt-in wrapper that sends a
  summarization prompt to a real :class:`ModelPort` and returns the
  resulting assistant text. CLI surfaces wire it in when running
  against a live model.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Iterable

from harnesslab.core.models import Message, Session

Summarizer = Callable[[list[Message]], str]

COMPACT_COMMAND = "/compact"


class ModelOverflowError(Exception):
    """Raised by a model adapter when the API rejected the request
    because the context window is full.

    Carries an optional ``estimated_tokens`` so the loop can record
    "how much did we ask for" in the overflow-triggered
    ``compaction_started`` event.
    """

    def __init__(self, message: str, *, estimated_tokens: int | None = None) -> None:
        super().__init__(message)
        self.estimated_tokens = estimated_tokens


def estimate_tokens(text: str) -> int:
    """A coarse ``len(text) // 4`` estimate.

    ``max(1, …)`` keeps even the empty string at a cost of one token
    so a long conversation of one-character messages still trips the
    threshold eventually.
    """

    if not text:
        return 1
    return max(1, len(text) // 4)


def parse_compact_command(user_input: str) -> bool:
    """Return True when ``user_input`` is an explicit ``/compact`` request."""

    return user_input.strip() == COMPACT_COMMAND


def format_message_for_summary(m: Message) -> str:
    """One transcript line for LLM or operator-facing compaction summaries."""

    parts: list[str] = [f"[{m.role}]"]
    if m.role == "assistant" and m.reasoning_text and m.reasoning_text.strip():
        thinking = " ".join(m.reasoning_text.split())
        if len(thinking) > 320:
            thinking = thinking[:317].rstrip() + "…"
        parts.append(f"(thinking: {thinking})")
    body = m.content.strip()
    if body:
        parts.append(body)
    return " ".join(parts)


def estimate_messages_tokens(messages: Iterable[Message]) -> int:
    """Sum :func:`estimate_tokens` across every message's content."""

    return sum(estimate_tokens(m.content) for m in messages)


def should_compact(messages: list[Message], *, threshold_tokens: int) -> bool:
    """Return True when the conversation needs compaction.

    The threshold is the *upper* bound the loop is willing to send;
    crossing it triggers compaction before the next model call. The
    function is pure so trace events can attach the exact estimate
    that drove the decision.
    """

    if not messages:
        return False
    return estimate_messages_tokens(messages) > threshold_tokens


def compact_messages(
    messages: list[Message],
    *,
    keep_last: int,
    summarizer: Summarizer | None = None,
    now: datetime | None = None,
    new_id: Callable[[str], str] | None = None,
) -> tuple[list[Message], dict]:
    """Compact older messages into a single summary message.

    Returns ``(new_messages, stats)`` where ``stats`` is the payload
    fragment that the loop attaches to the
    ``compaction_completed`` trace event.

    Defaults are picked so the function works without any wiring:
    a deterministic timestamp is supplied by the caller when
    determinism matters (eval, replay), and a built-in pseudo-id
    keeps the summary message valid when ``new_id`` is not supplied.
    """

    if keep_last < 0:
        raise ValueError(f"keep_last must be >= 0, got {keep_last}")

    if not messages:
        return [], {
            "kept_messages": 0,
            "removed_messages": 0,
            "summary_chars": 0,
        }

    if len(messages) <= keep_last:
        return list(messages), {
            "kept_messages": len(messages),
            "removed_messages": 0,
            "summary_chars": 0,
        }

    older = messages[: len(messages) - keep_last] if keep_last else list(messages)
    recent = messages[len(messages) - keep_last :] if keep_last else []
    summary_text = (summarizer or _fallback_summarizer)(older)
    summary_msg = Message(
        id=(new_id or _default_id)("msg"),
        role="system",
        content=summary_text,
        created_at=now or datetime.now(UTC),
        session_id=older[0].session_id,
    )
    return [summary_msg, *recent], {
        "kept_messages": len(recent),
        "removed_messages": len(older),
        "summary_chars": len(summary_text),
    }


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------


def _fallback_summarizer(older: list[Message]) -> str:
    """Deterministic, LLM-free summary.

    Lists message counts by role and the first non-system message's
    opening line. This is enough to keep the agent oriented after a
    compaction round without depending on a remote model — and it
    keeps eval / replay traces reproducible.
    """

    role_counts: dict[str, int] = {}
    reasoning_assistant = 0
    for m in older:
        role_counts[m.role] = role_counts.get(m.role, 0) + 1
        if m.role == "assistant" and m.reasoning_text and m.reasoning_text.strip():
            reasoning_assistant += 1
    roles_summary = ", ".join(
        f"{count} {role}" for role, count in sorted(role_counts.items())
    )

    opening_line = ""
    for m in older:
        if m.role == "system":
            continue
        for line in m.content.splitlines():
            stripped = line.strip()
            if stripped:
                opening_line = stripped if len(stripped) <= 200 else stripped[:197] + "..."
                break
        if opening_line:
            break

    lines = [
        "<system-reminder>",
        f"[Compacted earlier conversation: {len(older)} messages ({roles_summary})]",
    ]
    if reasoning_assistant:
        lines.append(
            f"Dropped raw thinking from {reasoning_assistant} compacted assistant "
            "message(s). Use /remember for notes that must survive compaction."
        )
    if opening_line:
        lines.append(f"First exchange opened with: {opening_line!r}")
    lines.append("</system-reminder>")
    return "\n".join(lines)


def _default_id(prefix: str) -> str:
    return f"{prefix}_compaction"


# ---------------------------------------------------------------------------
# live summarizer (opt-in)
# ---------------------------------------------------------------------------


_SUMMARIZER_PROMPT = (
    "<system-reminder>\n"
    "You are summarizing a long agent conversation so the agent can "
    "continue in a fresh, shorter context. Produce a faithful, neutral "
    "summary in 8 short bullet points or fewer. Capture: the user's goal, "
    "the decisions made, the tools called and their key results, and any "
    "open questions or pending TODOs. Do not invent facts; do not editorialise.\n"
    "</system-reminder>"
)


class LiveSummarizer:
    """Summarize older messages via a live :class:`ModelPort`.

    Wraps the model in a short prompt that asks for a faithful
    bullet-point summary. The result is fenced in ``<system-reminder>``
    markers so the next model call can tell the summary apart from
    real conversation.
    """

    def __init__(self, model) -> None:  # type: ignore[no-untyped-def]
        self._model = model

    def __call__(self, older: list[Message]) -> str:
        transcript = "\n".join(
            format_message_for_summary(m)
            for m in older
            if m.content or m.reasoning_text
        )
        # Build an ephemeral session whose only message is the
        # summarization prompt + transcript. The model never sees the
        # real session; this keeps summarization side-effect free.
        scratch = Session(goal="(compaction-summary)")
        scratch.messages.append(
            Message(
                role="user",
                content=f"{_SUMMARIZER_PROMPT}\n\nTranscript:\n{transcript}",
                session_id=scratch.id,
            )
        )
        decision = self._model.decide(scratch, _SUMMARIZER_PROMPT)
        body = (decision.assistant_message or "").strip()
        if not body:
            return _fallback_summarizer(older)
        return (
            "<system-reminder>\n"
            f"[Compacted earlier conversation: {len(older)} messages]\n"
            f"{body}\n"
            "</system-reminder>"
        )
