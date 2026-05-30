"""Group failure spans + eval failures by fingerprint into clusters."""

from __future__ import annotations

from pydantic import BaseModel, Field

from harnesslab.core.models import SpanRecord
from harnesslab.eval.task import TaskResult
from harnesslab.improve.fingerprint import (
    fingerprint_for_eval_failure,
    fingerprint_for_span,
)

_SAMPLE_CAP = 3


class Cluster(BaseModel):
    kind: str
    signature: str
    occurrences: int
    sample_spans: list[SpanRecord] = Field(default_factory=list)
    sample_task_failures: list[tuple[str, str]] = Field(default_factory=list)


def build_clusters(
    spans: list[SpanRecord],
    eval_results: list[TaskResult] | None = None,
    *,
    min_occurrences: int = 2,
) -> list[Cluster]:
    """Build clusters with at least ``min_occurrences`` occurrences.

    Sort order is deterministic: ``(-occurrences, signature)``.
    """

    buckets: dict[tuple[str, str], dict] = {}

    for span in spans:
        fp = fingerprint_for_span(span)
        if fp is None:
            continue
        bucket = buckets.setdefault(fp, {"spans": [], "task_failures": []})
        bucket["spans"].append(span)

    if eval_results:
        for result in eval_results:
            if result.passed:
                continue
            for failure in result.failures:
                fp = fingerprint_for_eval_failure(result.task_name, failure)
                bucket = buckets.setdefault(fp, {"spans": [], "task_failures": []})
                bucket["task_failures"].append((result.task_name, failure))

    clusters: list[Cluster] = []
    for (kind, signature), bucket in buckets.items():
        total = len(bucket["spans"]) + len(bucket["task_failures"])
        if total < min_occurrences:
            continue
        clusters.append(
            Cluster(
                kind=kind,
                signature=signature,
                occurrences=total,
                sample_spans=bucket["spans"][:_SAMPLE_CAP],
                sample_task_failures=bucket["task_failures"][:_SAMPLE_CAP],
            )
        )

    clusters.sort(key=lambda c: (-c.occurrences, c.signature))
    return clusters
