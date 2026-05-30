"""Extract a (kind, signature) fingerprint from failure spans.

Fingerprints group in ``cluster.build_clusters``. Compact form:

    tool_failure:tool.read_file:<short_error>
    policy_denial:tool.write_file:<short_reason>
    invalid_args:tool.write_file:<short_error>
    eval:<task_name>:<short_failure>

Successful tool spans (``harnesslab.tool.ok=true``) return ``None``.
"""

from __future__ import annotations

from harnesslab.core.models import SpanRecord
from harnesslab.telemetry.span_attributes import HARNESSLAB_TOOL_NAME, HARNESSLAB_TOOL_OK

_SHORT_LIMIT = 60


def fingerprint_for_span(span: SpanRecord) -> tuple[str, str] | None:
    """Return ``(kind, signature)`` for a failure span, else ``None``."""

    if span.name.startswith("tool.") and not span.name.startswith("tool.hooks."):
        tool = str(span.attributes.get(HARNESSLAB_TOOL_NAME) or span.name.split(".", 1)[-1])
        if span.attributes.get(HARNESSLAB_TOOL_OK) is True:
            return None
        for event in span.events:
            if event.name == "tool.policy_denied":
                reason = _short(str(event.attributes.get("reason") or ""))
                return "policy_denial", f"tool_denied:{tool}:{reason}"
            if event.name == "tool.args_invalid":
                error = _short(str(event.attributes.get("error") or ""))
                return "invalid_args", f"tool_invalid_args:{tool}:{error}"
        error = _short(str(span.status_message or span.attributes.get("error") or ""))
        return "tool_failure", f"tool_executed:{tool}:{error}"

    return None


def fingerprint_for_eval_failure(task_name: str, failure: str) -> tuple[str, str]:
    return "eval_regression", f"eval:{task_name}:{_short(failure, 80)}"


def _short(value: str, limit: int = _SHORT_LIMIT) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
