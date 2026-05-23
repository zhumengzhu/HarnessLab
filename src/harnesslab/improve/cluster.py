"""Group failure events + eval failures by fingerprint into clusters."""

from __future__ import annotations

from pydantic import BaseModel, Field

from harnesslab.core.models import TraceEvent
from harnesslab.eval.task import TaskResult
from harnesslab.improve.fingerprint import (
    fingerprint_for_eval_failure,
    fingerprint_for_event,
)

_SAMPLE_CAP = 3


class Cluster(BaseModel):
    kind: str
    signature: str
    occurrences: int
    sample_events: list[TraceEvent] = Field(default_factory=list)
    sample_task_failures: list[tuple[str, str]] = Field(default_factory=list)


def build_clusters(
    events: list[TraceEvent],
    eval_results: list[TaskResult] | None = None,
    *,
    min_occurrences: int = 2,
) -> list[Cluster]:
    """Build clusters with at least ``min_occurrences`` occurrences.

    Sort order is deterministic: ``(-occurrences, signature)``.
    """

    buckets: dict[tuple[str, str], dict] = {}

    for event in events:
        fp = fingerprint_for_event(event)
        if fp is None:
            continue
        bucket = buckets.setdefault(fp, {"events": [], "task_failures": []})
        bucket["events"].append(event)

    if eval_results:
        for result in eval_results:
            if result.passed:
                continue
            for failure in result.failures:
                fp = fingerprint_for_eval_failure(result.task_name, failure)
                bucket = buckets.setdefault(fp, {"events": [], "task_failures": []})
                bucket["task_failures"].append((result.task_name, failure))

    clusters: list[Cluster] = []
    for (kind, signature), bucket in buckets.items():
        total = len(bucket["events"]) + len(bucket["task_failures"])
        if total < min_occurrences:
            continue
        clusters.append(
            Cluster(
                kind=kind,
                signature=signature,
                occurrences=total,
                sample_events=bucket["events"][:_SAMPLE_CAP],
                sample_task_failures=bucket["task_failures"][:_SAMPLE_CAP],
            )
        )

    clusters.sort(key=lambda c: (-c.occurrences, c.signature))
    return clusters
