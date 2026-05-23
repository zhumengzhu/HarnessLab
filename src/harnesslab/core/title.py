"""Session title derivation and optional LLM auto-naming.

Initial titles come from :func:`derive_title_from_text` (first line of
the goal, truncated). After the **first** completed user turn, an
optional :class:`LiveTitleNamer` may replace that placeholder with a
short LLM-generated label.

Design constraints (robust / fast / low token):

- Runs at most once per session (``turn_count == 1`` after
  ``run_session`` returns).
- Sends only the first user message plus a short assistant excerpt
  (no full transcript, no tool spam).
- Expects a plain-text ``final`` reply; tool decisions fall back.
- Output is sanitized (single line, length cap, quote stripping).
- Failures never block the loop — the derived title stays in place.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from harnesslab.core.models import Message, Session

if TYPE_CHECKING:
    pass

TitleNamer = Callable[[Session], str | None]

TITLE_MAX_LEN = 60
USER_SNIPPET_MAX = 200
ASSISTANT_SNIPPET_MAX = 120

_TITLE_PROMPT = (
    "Generate a short chat title (3-6 words, same language as the user). "
    "Reply with ONLY the title text. No quotes, no wrapper, no explanation."
)


def derive_title_from_text(text: str) -> str:
    """Turn a goal or user input into a short, single-line label."""

    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) <= TITLE_MAX_LEN:
            return stripped
        return stripped[: TITLE_MAX_LEN - 1].rstrip() + "…"
    return "(no title)"


def sanitize_title(raw: str) -> str | None:
    """Normalize model output into a safe session title or ``None``."""

    text = " ".join(raw.strip().splitlines()).strip()
    if not text:
        return None
    for ch in ('"', "'", "「", "」", "『", "』"):
        text = text.strip(ch)
    text = text.strip().strip(".")
    if not text:
        return None
    if len(text) > TITLE_MAX_LEN:
        text = text[: TITLE_MAX_LEN - 1].rstrip() + "…"
    return text


def _snippet(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def build_title_prompt(session: Session) -> str:
    """Minimal prompt body for a one-shot title call."""

    user_msgs = [m for m in session.messages if m.role == "user"]
    asst_msgs = [m for m in session.messages if m.role == "assistant"]
    user_part = _snippet(
        user_msgs[0].content if user_msgs else session.goal,
        USER_SNIPPET_MAX,
    )
    lines = [_TITLE_PROMPT, f"User message: {user_part}"]
    if asst_msgs:
        lines.append(
            "Assistant reply excerpt: "
            + _snippet(asst_msgs[-1].content, ASSISTANT_SNIPPET_MAX)
        )
    return "\n".join(lines)


class LiveTitleNamer:
    """Name a session via a single cheap ``ModelPort.decide`` call."""

    def __init__(self, model) -> None:  # type: ignore[no-untyped-def]
        self._model = model

    def __call__(self, session: Session) -> str | None:
        scratch = Session(goal="(session-title)")
        scratch.messages.append(
            Message(
                role="user",
                content=build_title_prompt(session),
                session_id=scratch.id,
            )
        )
        decision = self._model.decide(scratch, "")
        if decision.kind == "tool":
            return None
        raw = decision.assistant_message or ""
        cleaned = sanitize_title(raw)
        if cleaned:
            return cleaned
        return derive_title_from_text(session.goal)
