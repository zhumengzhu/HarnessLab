"""Turn/session outcome signals for online arm updates."""

from __future__ import annotations

from harnesslab.core.models import Session


def session_outcome_success(session: Session) -> bool:
    """Conservative run-path reward: a clean ``final`` terminal turn."""

    return session.status == "done"
