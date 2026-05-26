"""DeepSeek thinking / reasoning_effort resolution for config + UI."""

from __future__ import annotations

from typing import Any

# UI + operator config expose a single effort selector:
#   disabled → non-thinking
#   high     → thinking enabled + reasoning_effort=high (API default)
#   max      → thinking enabled + reasoning_effort=max
DEEPSEEK_UI_EFFORTS: tuple[str, ...] = ("disabled", "high", "max")


def parse_deepseek_thinking_fields(
    *,
    thinking_raw: Any,
    reasoning_effort_raw: Any | None = None,
) -> tuple[str, str | None]:
    """Return ``(thinking_mode, reasoning_effort)`` for :class:`DeepSeekModel`."""

    effort_str = (
        str(reasoning_effort_raw).strip().lower()
        if reasoning_effort_raw is not None and str(reasoning_effort_raw).strip()
        else None
    )
    if isinstance(thinking_raw, str):
        key = thinking_raw.strip().lower()
        if key in {"disabled", "off", "none"}:
            return "disabled", None
        if key in {"high", "max"}:
            return "enabled", key
        if key == "enabled":
            return "enabled", effort_str or "high"
    if effort_str in {"high", "max"}:
        return "enabled", effort_str
    return "disabled", None


def deepseek_ui_effort(*, thinking_mode: str, reasoning_effort: str | None) -> str:
    if (thinking_mode or "disabled").strip().lower() != "enabled":
        return "disabled"
    effort = (reasoning_effort or "high").strip().lower()
    if effort == "max":
        return "max"
    return "high"


def apply_deepseek_ui_effort(effort: str) -> tuple[str, str | None]:
    key = effort.strip().lower()
    if key == "disabled":
        return "disabled", None
    if key == "max":
        return "enabled", "max"
    if key == "high":
        return "enabled", "high"
    raise ValueError(f"unsupported DeepSeek effort {effort!r} (use disabled, high, max)")
