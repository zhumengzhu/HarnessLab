"""Provider failover chain (Post-MVP P6)."""

from __future__ import annotations

from typing import Any

from harnesslab.core.models import Decision, Session
from harnesslab.telemetry.log import get_logger

_log = get_logger("providers.failover")

_FAILURE_PREFIXES = (
    "Anthropic request failed:",
    "OpenAI request failed:",
    "DeepSeek request failed:",
    "Gemini request failed:",
)


class FailoverModel:
    """Try configured backends in order until one returns a non-failure decision."""

    def __init__(self, models: list[Any], *, backend_labels: list[str] | None = None) -> None:
        if not models:
            raise ValueError("FailoverModel requires at least one backend")
        self._models = models
        self._backend_labels = backend_labels or [f"backend_{i}" for i in range(len(models))]
        self._last_call_meta: dict[str, Any] = {}

    def decide(self, session: Session, user_input: str) -> Decision:
        last_decision: Decision | None = None
        for index, model in enumerate(self._models):
            label = self._backend_labels[index]
            decision = model.decide(session, user_input)
            if not _is_failure_decision(decision):
                meta = {}
                if hasattr(model, "last_call_meta"):
                    meta = dict(model.last_call_meta())
                self._last_call_meta = {
                    **meta,
                    "failover_index": index,
                    "failover_backend": label,
                    "failover_attempts": index + 1,
                }
                if index > 0:
                    _log.warning(
                        "failover succeeded backend=%s attempt=%s session=%s",
                        label,
                        index + 1,
                        session.id,
                    )
                return decision
            last_decision = decision
            _log.warning(
                "failover attempt failed backend=%s session=%s",
                label,
                session.id,
            )

        self._last_call_meta = {
            "failover_index": len(self._models) - 1,
            "failover_backend": self._backend_labels[-1],
            "failover_attempts": len(self._models),
            "failover_exhausted": True,
        }
        if last_decision is not None:
            return last_decision
        return Decision(
            kind="final",
            assistant_message="All model backends failed.",
        )

    def last_call_meta(self) -> dict[str, Any]:
        return dict(self._last_call_meta)


def _is_failure_decision(decision: Decision) -> bool:
    if decision.kind != "final":
        return False
    message = decision.assistant_message or ""
    return any(message.startswith(prefix) for prefix in _FAILURE_PREFIXES)
