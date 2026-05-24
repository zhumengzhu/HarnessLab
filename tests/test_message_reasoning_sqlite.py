"""Message reasoning fields round-trip through SQLite (Post-MVP P1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from harnesslab.core.models import Message, Session
from harnesslab.session.sqlite_store import SqliteSessionStore


def test_message_reasoning_fields_persist(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "reasoning.sqlite")
    session = Session(
        id="ses_reason",
        goal="persist reasoning",
        created_at=datetime(2026, 5, 24, tzinfo=UTC),
        messages=[
            Message(
                id="msg_a",
                role="assistant",
                content="",
                created_at=datetime(2026, 5, 24, tzinfo=UTC),
                session_id="ses_reason",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "grep", "arguments": "{}"},
                    }
                ],
                reasoning_text="internal reasoning",
                provider_extra={"vendor": "deepseek"},
            )
        ],
    )
    store.create(session)
    loaded = store.get("ses_reason")
    assert loaded.messages[0].reasoning_text == "internal reasoning"
    assert loaded.messages[0].provider_extra == {"vendor": "deepseek"}
    store.close()
