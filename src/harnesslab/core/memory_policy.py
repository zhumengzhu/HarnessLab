"""Session-scoped memory read/write policy for ``MemoryStorePort``.

HarnessLab distinguishes two layers:

- **Session** — the live conversation timeline (``session.messages``).
  Subject to compaction; optimized for the next model call.
- **Memory** — a durable key/value store (``MemoryStorePort``) holding
  explicit user notes that survive compaction and are re-injected on
  later turns **within the same session**.

Phase 3.3 wires memory *onto* session: keys are namespaced by
``session_id``. Cross-session retrieval / vector RAG is explicitly out
of scope.

Writes happen only on the ``/remember <text>`` user command (no
automatic LLM extraction) so eval and replay stay stable.
"""

from __future__ import annotations

SESSION_MEMORY_SUFFIX = "notes"
REMEMBER_PREFIX = "/remember "
REMEMBER_BODY_MAX = 500


def session_memory_key(session_id: str) -> str:
    """Stable KV key for a session's rolling notes blob."""

    return f"session:{session_id}:{SESSION_MEMORY_SUFFIX}"


def format_memory_message(notes: str) -> str:
    """System text injected before the model sees a new user turn."""

    body = notes.strip()
    return (
        "Session memory (explicit notes saved via /remember in this session):\n"
        f"{body}"
    )


def parse_remember_command(user_input: str) -> str | None:
    """Return note body when ``user_input`` is ``/remember …``, else ``None``."""

    text = user_input.strip()
    if not text.startswith(REMEMBER_PREFIX):
        return None
    body = text[len(REMEMBER_PREFIX) :].strip()
    return body if body else None


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def format_remember_note(body: str) -> str:
    """One line stored for an explicit ``/remember`` command."""

    return f"[remember] {_clip(body, REMEMBER_BODY_MAX)!r}"


def append_note(existing: str | None, line: str) -> str:
    if not existing:
        return line
    return f"{existing.rstrip()}\n{line}"
