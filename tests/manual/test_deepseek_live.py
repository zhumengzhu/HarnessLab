"""Manual live test for DeepSeek integration.

This test is skipped by default. Run explicitly only when you want to
verify the real network/provider path:

    RUN_DEEPSEEK_LIVE=1 DEEPSEEK_API_KEY=... uv run pytest tests/manual/test_deepseek_live.py
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from harnesslab.core.models import Session
from harnesslab.providers.deepseek import DeepSeekModel

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DEEPSEEK_LIVE") != "1",
    reason="set RUN_DEEPSEEK_LIVE=1 to enable",
)


def test_live_deepseek_round_trip() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY missing")
    model = DeepSeekModel(
        tool_specs_provider=lambda: [],
    )
    session = Session(
        id="ses_live",
        goal="smoke",
        created_at=datetime.now(UTC),
    )
    decision = model.decide(session, "Reply with one short sentence.")
    assert decision.kind == "assistant"
    assert decision.assistant_message
