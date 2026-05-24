"""Optional live DeepSeek smoke tests (real API, not in default CI).

Verifies **connectivity only** — thinking on/off completes without transport
errors. Does not assert tool use, reasoning content, or model quality.

    RUN_DEEPSEEK_LIVE=1 DEEPSEEK_API_KEY=... \\
      uv run pytest tests/manual/test_deepseek_live.py -m network -v -rs -s

Logs go to **stderr**. Use ``-s`` so pytest does not capture them.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from harnesslab.core.models import Session
from harnesslab.providers.deepseek import DeepSeekModel
from harnesslab.telemetry.log import configure_logging, get_logger

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("RUN_DEEPSEEK_LIVE") != "1",
        reason="set RUN_DEEPSEEK_LIVE=1 to enable live DeepSeek tests",
    ),
]

configure_logging(force=True)
_log = get_logger("tests.manual.deepseek_live")

_LIVE_MODEL = "deepseek-v4-flash"
_SMOKE_PROMPT = "Reply with exactly one short English sentence. No tools."


def _require_api_key() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY missing")


def _live_model(*, thinking: str) -> DeepSeekModel:
    return DeepSeekModel(
        tool_specs_provider=lambda: [],
        model_name=_LIVE_MODEL,
        thinking_mode=thinking,
    )


def _assert_basic_call_ok(label: str, decision, meta: dict[str, object]) -> None:
    _log.info(
        "%s kind=%s model=%s tokens=%s reasoning=%s message=%r",
        label,
        decision.kind,
        meta.get("model_name"),
        meta.get("total_tokens"),
        bool(meta.get("reasoning_text")),
        (decision.assistant_message or "")[:80],
    )
    assert not (decision.assistant_message or "").startswith("DeepSeek request failed")
    assert decision.kind == "final"
    assert decision.assistant_message
    assert meta.get("model_name") == _LIVE_MODEL


def test_live_deepseek_v4_flash_thinking_disabled() -> None:
    """Smoke: ``thinking.type=disabled`` returns a normal final reply."""

    _require_api_key()
    model = _live_model(thinking="disabled")
    session = Session(id="ses_live_off", goal="smoke", created_at=datetime.now(UTC))
    decision = model.decide(session, _SMOKE_PROMPT)
    _assert_basic_call_ok("thinking_disabled", decision, model.last_call_meta())


def test_live_deepseek_v4_flash_thinking_enabled() -> None:
    """Smoke: ``thinking.type=enabled`` returns a normal final reply."""

    _require_api_key()
    model = _live_model(thinking="enabled")
    session = Session(id="ses_live_on", goal="smoke", created_at=datetime.now(UTC))
    decision = model.decide(session, _SMOKE_PROMPT)
    _assert_basic_call_ok("thinking_enabled", decision, model.last_call_meta())
