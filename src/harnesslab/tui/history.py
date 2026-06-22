"""Pure helpers for in-session chat history search (TUI ``/search``)."""

from __future__ import annotations

from dataclasses import dataclass

from harnesslab.core.models import Message


@dataclass(frozen=True)
class HistoryHit:
    index: int
    role: str
    snippet: str


def search_messages(
    messages: list[Message],
    query: str,
    *,
    max_hits: int = 20,
    context: int = 40,
) -> list[HistoryHit]:
    """Case-insensitive substring search over message content.

    Returns at most ``max_hits`` hits, each with the message index, role,
    and a single-line snippet centred on the first match (``…`` marks
    truncation). An empty query returns no hits.
    """

    needle = query.strip().lower()
    if not needle:
        return []
    hits: list[HistoryHit] = []
    for index, message in enumerate(messages):
        content = message.content or ""
        pos = content.lower().find(needle)
        if pos == -1:
            continue
        start = max(0, pos - context)
        end = min(len(content), pos + len(needle) + context)
        snippet = content[start:end].replace("\n", " ").strip()
        if start > 0:
            snippet = f"…{snippet}"
        if end < len(content):
            snippet = f"{snippet}…"
        hits.append(HistoryHit(index=index, role=message.role, snippet=snippet))
        if len(hits) >= max_hits:
            break
    return hits
