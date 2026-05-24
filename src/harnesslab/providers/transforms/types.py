"""Shared transform result types (Post-MVP P1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnesslab.core.models import Decision


@dataclass
class ParsedModelTurn:
    """Normalized output from one provider response."""

    decision: Decision
    reasoning_text: str | None = None
    provider_extra: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReplayPolicy:
    """Which stored fields must round-trip on the next model call."""

    include_reasoning_in_tool_loop: bool = False
    drop_reasoning_on_new_user_turn: bool = True
