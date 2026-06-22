"""Pydantic model for an advisory improvement proposal."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProposalStatus = Literal["open", "accepted", "rejected", "superseded"]


class Proposal(BaseModel):
    id: str
    status: ProposalStatus = "open"
    kind: str
    cluster_signature: str
    occurrences: int
    trials: int = 0
    posterior_failure_rate: float | None = None
    credible_interval: tuple[float, float] | None = None
    priority: float | None = None
    generated_at: datetime
    related_files: list[str] = Field(default_factory=list)
    suggested_actions: list[str]
    sample_events: list[dict] = Field(default_factory=list)
    sample_task_failures: list[tuple[str, str]] = Field(default_factory=list)
