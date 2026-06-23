"""Data models for online arm selection."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OnlineArm(BaseModel):
    """One selectable system-prompt variant (an bandit arm)."""

    id: str
    label: str = ""
    system_prompt: str
    source: str = "manual"  # baseline | proposal | config


class ArmStats(BaseModel):
    successes: int = 0
    trials: int = 0


class SelectionResult(BaseModel):
    arm: OnlineArm
    sample: float
    successes: int
    trials: int
    candidates: list[str] = Field(default_factory=list)
