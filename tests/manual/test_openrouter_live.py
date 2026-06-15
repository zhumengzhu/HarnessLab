"""Optional live OpenRouter / OpenAI-proxy smoke (real API, not in default CI).

    RUN_OPENROUTER_LIVE=1 OPENAI_API_KEY=sk-or-v1-... \\
      OPENAI_BASE_URL=https://openrouter.ai/api/v1 \\
      uv run pytest tests/manual/test_openrouter_live.py -m network -v -rs
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from harnesslab.core.models import Session
from harnesslab.core.operator_config import OperatorConfig
from harnesslab.providers.registry import create_model

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("RUN_OPENROUTER_LIVE") != "1",
        reason="set RUN_OPENROUTER_LIVE=1 to enable OpenRouter live tests",
    ),
]


def _require_proxy_env() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY missing")
    base = (os.getenv("OPENAI_BASE_URL") or "").strip()
    if not base:
        pytest.skip("OPENAI_BASE_URL missing (set to https://openrouter.ai/api/v1)")


def test_openrouter_openai_backend_smoke() -> None:
    _require_proxy_env()
    config = OperatorConfig(model_backend="openai")
    model = create_model(
        "openai",
        config=config,
        tool_specs_provider=lambda: [],
        dynamic_blocks_provider=lambda _session: [],
    )
    session = Session(id="ses_openrouter_live", goal="smoke", created_at=datetime.now(UTC))
    decision = model.decide(session, "Reply with exactly: proxy ok")
    assert decision.kind in {"final", "assistant"}
    assert decision.assistant_message.strip()
