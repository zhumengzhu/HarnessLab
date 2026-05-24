"""Optional live Anthropic-wire smoke via DeepSeek's Anthropic-compatible API.

Exercises ``AnthropicModel`` + Messages transport against
``https://api.deepseek.com/anthropic`` using ``DEEPSEEK_API_KEY`` — no Claude
key required. Connectivity only; does not assert tool use or model quality.

    RUN_ANTHROPIC_DEEPSEEK_LIVE=1 DEEPSEEK_API_KEY=... \\
      uv run pytest tests/manual/test_anthropic_deepseek_live.py -m network -v -rs -s

Logs go to **stderr**. Use ``-s`` so pytest does not capture them.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from harnesslab.core.models import Session
from harnesslab.providers.anthropic import DEEPSEEK_ANTHROPIC_BASE_URL, AnthropicModel
from harnesslab.providers.model_resolve import DEFAULT_DEEPSEEK_MODEL
from harnesslab.telemetry.log import configure_logging, get_logger

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("RUN_ANTHROPIC_DEEPSEEK_LIVE") != "1",
        reason="set RUN_ANTHROPIC_DEEPSEEK_LIVE=1 to enable Anthropic-wire live tests",
    ),
]

configure_logging(force=True)
_log = get_logger("tests.manual.anthropic_deepseek_live")

_LIVE_MODEL = DEFAULT_DEEPSEEK_MODEL
_SMOKE_PROMPT = "Reply with exactly one short English sentence. No tools."


def _require_api_key() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY missing")


def _live_model(*, thinking: str) -> AnthropicModel:
    return AnthropicModel(
        tool_specs_provider=lambda: [],
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=DEEPSEEK_ANTHROPIC_BASE_URL,
        model_name=_LIVE_MODEL,
        thinking_mode=thinking,
        max_tokens=512,
    )


def _assert_basic_call_ok(label: str, decision, meta: dict[str, object]) -> None:
    _log.info(
        "%s kind=%s model=%s base_url=%s tokens=%s reasoning=%s message=%r",
        label,
        decision.kind,
        meta.get("model_name"),
        meta.get("base_url"),
        meta.get("total_tokens"),
        bool(meta.get("reasoning_text")),
        (decision.assistant_message or "")[:80],
    )
    assert not (decision.assistant_message or "").startswith("Anthropic request failed")
    assert decision.kind == "final"
    assert decision.assistant_message
    assert meta.get("model_name") == _LIVE_MODEL
    assert meta.get("api_family") == "anthropic_messages"
    assert meta.get("base_url") == DEEPSEEK_ANTHROPIC_BASE_URL


def test_live_anthropic_wire_deepseek_thinking_disabled() -> None:
    """Smoke: Messages API with no ``thinking`` returns a final reply."""

    _require_api_key()
    model = _live_model(thinking="disabled")
    session = Session(id="ses_anthropic_off", goal="smoke", created_at=datetime.now(UTC))
    decision = model.decide(session, _SMOKE_PROMPT)
    _assert_basic_call_ok("thinking_disabled", decision, model.last_call_meta())


def test_live_anthropic_wire_deepseek_thinking_enabled() -> None:
    """Smoke: Messages API with ``thinking.type=enabled`` returns a final reply."""

    _require_api_key()
    model = _live_model(thinking="enabled")
    session = Session(id="ses_anthropic_on", goal="smoke", created_at=datetime.now(UTC))
    decision = model.decide(session, _SMOKE_PROMPT)
    _assert_basic_call_ok("thinking_enabled", decision, model.last_call_meta())
