"""Tests for provider failover chain (Post-MVP P6)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from harnesslab.core.models import Decision, Message, Session
from harnesslab.core.operator_config import OperatorConfig
from harnesslab.core.simple_model import SimpleModel
from harnesslab.providers.failover import FailoverModel
from harnesslab.providers.registry import create_model


class _FailingModel:
    def decide(self, session: Session, user_input: str) -> Decision:
        return Decision(
            kind="final",
            assistant_message="DeepSeek request failed: APIStatusError: 503",
        )

    def last_call_meta(self) -> dict[str, str]:
        return {"provider": "deepseek"}


def _session() -> Session:
    return Session(
        id="ses_failover",
        goal="demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[
            Message(
                id="msg_1",
                role="user",
                content="hello",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                session_id="ses_failover",
            )
        ],
    )


def test_failover_tries_next_backend() -> None:
    model = FailoverModel([_FailingModel(), SimpleModel()], backend_labels=["deepseek", "simple"])
    decision = model.decide(_session(), "hello")
    assert decision.kind == "final"
    assert decision.assistant_message is not None
    assert "failed" not in decision.assistant_message.lower()
    meta = model.last_call_meta()
    assert meta["failover_backend"] == "simple"
    assert meta["failover_index"] == 1


def test_failover_exhausted_returns_last_failure() -> None:
    model = FailoverModel([_FailingModel(), _FailingModel()], backend_labels=["a", "b"])
    decision = model.decide(_session(), "hello")
    assert decision.assistant_message.startswith("DeepSeek request failed:")
    assert model.last_call_meta()["failover_exhausted"] is True


def test_registry_wraps_failover_when_opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    config = OperatorConfig(
        model_backend="deepseek",
        model_failover_enabled=True,
        model_fallbacks=("simple",),
    )
    model = create_model(
        "deepseek",
        config=config,
        tool_specs_provider=lambda: [],
        dynamic_blocks_provider=lambda _s: [],
    )
    assert isinstance(model, FailoverModel)
