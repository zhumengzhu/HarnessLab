"""Session- and workspace-scoped memory read/write policy for ``MemoryStorePort``.

HarnessLab distinguishes three layers:

- **Session** — the live conversation timeline (``session.messages``).
  Subject to compaction; optimized for the next model call.
- **Session memory** — durable notes keyed by ``session_id``; re-injected on
  later turns **within the same session**.
- **Workspace memory** (Phase 4.5 lite) — explicit notes keyed by workspace
  root; re-injected on every new turn in **any session** for that workspace.

Cross-session vector RAG is explicitly out of scope.

Writes happen only on ``/remember`` and ``/remember-global`` user commands
(no automatic LLM extraction) so eval and replay stay stable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

SESSION_MEMORY_SUFFIX = "notes"
WORKSPACE_MEMORY_SUFFIX = "notes"
REMEMBER_PREFIX = "/remember "
REMEMBER_GLOBAL_PREFIX = "/remember-global "
REMEMBER_BODY_MAX = 500


def session_memory_key(session_id: str) -> str:
    """Stable KV key for a session's rolling notes blob."""

    return f"session:{session_id}:{SESSION_MEMORY_SUFFIX}"


def workspace_memory_key(workspace_root: Path | str) -> str:
    """Stable KV key for workspace-scoped notes (hash of resolved root)."""

    root = str(Path(workspace_root).resolve())
    digest = hashlib.sha256(root.encode()).hexdigest()[:16]
    return f"workspace:{digest}:{WORKSPACE_MEMORY_SUFFIX}"


def format_memory_message(notes: str) -> str:
    """System text injected before the model sees a new user turn."""

    body = notes.strip()
    return (
        "Session memory (explicit notes saved via /remember in this session):\n"
        f"{body}"
    )


def format_workspace_memory_message(notes: str) -> str:
    """System text for workspace-scoped notes injected on every turn."""

    body = notes.strip()
    return (
        "Workspace memory (explicit notes saved via /remember-global in this "
        f"workspace):\n{body}"
    )


def parse_remember_command(user_input: str) -> str | None:
    """Return note body when ``user_input`` is ``/remember …``, else ``None``."""

    text = user_input.strip()
    if not text.startswith(REMEMBER_PREFIX):
        return None
    if text.startswith(REMEMBER_GLOBAL_PREFIX):
        return None
    body = text[len(REMEMBER_PREFIX) :].strip()
    return body if body else None


def parse_remember_global_command(user_input: str) -> str | None:
    """Return note body for ``/remember-global …``, else ``None``."""

    text = user_input.strip()
    if not text.startswith(REMEMBER_GLOBAL_PREFIX):
        return None
    body = text[len(REMEMBER_GLOBAL_PREFIX) :].strip()
    return body if body else None


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def format_remember_note(body: str) -> str:
    """One line stored for an explicit ``/remember`` command."""

    return f"[remember] {_clip(body, REMEMBER_BODY_MAX)!r}"


def format_remember_global_note(body: str) -> str:
    """One line stored for an explicit ``/remember-global`` command."""

    return f"[remember-global] {_clip(body, REMEMBER_BODY_MAX)!r}"


def append_note(existing: str | None, line: str) -> str:
    if not existing:
        return line
    return f"{existing.rstrip()}\n{line}"
