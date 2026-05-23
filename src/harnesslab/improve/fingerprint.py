"""Extract a (kind, signature) fingerprint from a failure event.

The signature is what `cluster.build_clusters` groups on. It is
deliberately compact and human-readable:

    tool_executed:<tool>:<short_error>
    tool_denied:<tool>:<short_reason>
    tool_invalid_args:<tool>:<short_error>
    eval:<task_name>:<short_failure>

Successful events (e.g. tool_executed with ok=true, decision_made,
session_started) return None.
"""

from __future__ import annotations

from harnesslab.core.models import TraceEvent

_SHORT_LIMIT = 60


def fingerprint_for_event(event: TraceEvent) -> tuple[str, str] | None:
    """Return ``(kind, signature)`` for a failure event, else ``None``."""

    if event.event_type == "tool_executed":
        if event.payload.get("ok"):
            return None
        tool = str(event.payload.get("tool", "?"))
        error = _short(str(event.payload.get("error") or ""))
        return "tool_failure", f"tool_executed:{tool}:{error}"

    if event.event_type == "tool_denied":
        tool = str(event.payload.get("tool", "?"))
        reason = _short(str(event.payload.get("reason") or ""))
        return "policy_denial", f"tool_denied:{tool}:{reason}"

    if event.event_type == "tool_invalid_args":
        tool = str(event.payload.get("tool", "?"))
        error = _short(str(event.payload.get("error") or ""))
        return "invalid_args", f"tool_invalid_args:{tool}:{error}"

    return None


def fingerprint_for_eval_failure(task_name: str, failure: str) -> tuple[str, str]:
    return "eval_regression", f"eval:{task_name}:{_short(failure, 80)}"


def _short(value: str, limit: int = _SHORT_LIMIT) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
