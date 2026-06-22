"""Group failure spans + eval failures by fingerprint into clusters.

Each cluster carries a Beta-Binomial posterior failure-rate estimate
(Layer A of ``docs/research/bayesian-self-evolution.md``). The denominator
("trials") is the total number of invocations of the offending tool — not
just its failures — so a 2/2 failure on a rarely-used tool can outrank a
50/1000 failure on a heavily-used one. ``occurrences`` (the numerator) is
preserved for backward compatibility.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from harnesslab.core.models import SpanRecord
from harnesslab.eval.task import TaskResult
from harnesslab.improve.fingerprint import (
    fingerprint_for_eval_failure,
    fingerprint_for_span,
)
from harnesslab.improve.scoring import empirical_bayes_prior, estimate_rate
from harnesslab.telemetry.span_attributes import HARNESSLAB_TOOL_NAME

_SAMPLE_CAP = 3


class Cluster(BaseModel):
    kind: str
    signature: str
    occurrences: int
    trials: int = 0
    posterior_failure_rate: float | None = None
    credible_interval: tuple[float, float] | None = None
    priority: float | None = None
    sample_spans: list[SpanRecord] = Field(default_factory=list)
    sample_task_failures: list[tuple[str, str]] = Field(default_factory=list)


def _tool_name(span: SpanRecord) -> str:
    return str(span.attributes.get(HARNESSLAB_TOOL_NAME) or span.name.split(".", 1)[-1])


def _is_tool_span(span: SpanRecord) -> bool:
    return span.name.startswith("tool.") and not span.name.startswith("tool.hooks.")


def build_clusters(
    spans: list[SpanRecord],
    eval_results: list[TaskResult] | None = None,
    *,
    min_occurrences: int = 2,
) -> list[Cluster]:
    """Build clusters with at least ``min_occurrences`` occurrences.

    Sort order is deterministic: ``(-priority, -occurrences, signature)`` so
    the highest-confidence failure rate surfaces first, with occurrence count
    and signature as stable tie-breakers.
    """

    buckets: dict[tuple[str, str], dict] = {}
    tool_totals: dict[str, int] = {}

    for span in spans:
        if not _is_tool_span(span):
            continue
        tool = _tool_name(span)
        tool_totals[tool] = tool_totals.get(tool, 0) + 1
        fp = fingerprint_for_span(span)
        if fp is None:
            continue
        bucket = buckets.setdefault(fp, {"spans": [], "task_failures": [], "tool": tool})
        bucket["spans"].append(span)

    if eval_results:
        for result in eval_results:
            if result.passed:
                continue
            for failure in result.failures:
                fp = fingerprint_for_eval_failure(result.task_name, failure)
                bucket = buckets.setdefault(
                    fp, {"spans": [], "task_failures": [], "tool": None}
                )
                bucket["task_failures"].append((result.task_name, failure))

    global_failures = sum(
        len(b["spans"]) + len(b["task_failures"]) for b in buckets.values()
    )
    eval_failures = sum(len(b["task_failures"]) for b in buckets.values())
    global_trials = sum(tool_totals.values()) + eval_failures
    prior = empirical_bayes_prior(global_failures, global_trials)

    clusters: list[Cluster] = []
    for (kind, signature), bucket in buckets.items():
        failures = len(bucket["spans"]) + len(bucket["task_failures"])
        if failures < min_occurrences:
            continue
        tool = bucket.get("tool")
        # Tool clusters use the tool's total invocation count as denominator;
        # deterministic eval failures have no success side, so trials == failures.
        trials = tool_totals.get(tool, failures) if tool is not None else failures
        estimate = estimate_rate(failures, trials, prior=prior)
        clusters.append(
            Cluster(
                kind=kind,
                signature=signature,
                occurrences=failures,
                trials=estimate.trials,
                posterior_failure_rate=estimate.mean,
                credible_interval=(estimate.low, estimate.high),
                priority=estimate.low,
                sample_spans=bucket["spans"][:_SAMPLE_CAP],
                sample_task_failures=bucket["task_failures"][:_SAMPLE_CAP],
            )
        )

    clusters.sort(
        key=lambda c: (-(c.priority or 0.0), -c.occurrences, c.signature)
    )
    return clusters
