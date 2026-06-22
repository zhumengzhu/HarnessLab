"""Generate proposals from clusters; dedupe against on-disk proposals."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path

from harnesslab.core.models import SpanRecord
from harnesslab.eval.task import TaskResult
from harnesslab.improve.cluster import build_clusters
from harnesslab.improve.proposal import Proposal
from harnesslab.improve.templates import related_files_for, suggestions_for

_SIG_HEADER = re.compile(r'^cluster_signature:\s*"(.*)"\s*$')


def generate(
    spans: list[SpanRecord],
    eval_results: list[TaskResult] | None = None,
    *,
    min_occurrences: int = 2,
    now: datetime | None = None,
) -> list[Proposal]:
    """Build clusters from spans + eval results and emit a Proposal each."""

    now = now or datetime.now(UTC)
    clusters = build_clusters(
        spans, eval_results, min_occurrences=min_occurrences
    )
    proposals: list[Proposal] = []
    for cluster in clusters:
        sig8 = sha1(cluster.signature.encode("utf-8")).hexdigest()[:8]
        ts = now.strftime("%Y%m%d%H%M")
        proposals.append(
            Proposal(
                id=f"prop_{ts}_{sig8}",
                status="open",
                kind=cluster.kind,
                cluster_signature=cluster.signature,
                occurrences=cluster.occurrences,
                trials=cluster.trials,
                posterior_failure_rate=cluster.posterior_failure_rate,
                credible_interval=cluster.credible_interval,
                priority=cluster.priority,
                generated_at=now,
                related_files=related_files_for(cluster.kind),
                suggested_actions=suggestions_for(cluster.kind),
                sample_events=[
                    s.model_dump(mode="json") for s in cluster.sample_spans
                ],
                sample_task_failures=list(cluster.sample_task_failures),
            )
        )
    return proposals


def dedupe_against_existing(
    new_proposals: list[Proposal],
    proposals_dir: Path,
) -> list[Proposal]:
    """Drop proposals whose ``cluster_signature`` already has an *open*
    proposal on disk.

    Accepted / rejected / superseded proposals do not block re-emission
    — a recurring problem after rejection is still worth surfacing.
    """

    if not proposals_dir.exists():
        return list(new_proposals)
    open_signatures = _load_open_signatures(proposals_dir)
    return [
        p for p in new_proposals if p.cluster_signature not in open_signatures
    ]


def _load_open_signatures(proposals_dir: Path) -> set[str]:
    found: set[str] = set()
    for path in sorted(proposals_dir.glob("prop_*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        signature, status = _parse_front_matter(text)
        if signature is None:
            continue
        if status == "open":
            found.add(signature)
    return found


def _parse_front_matter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, "open"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "open"
    block = text[3:end]
    signature: str | None = None
    status = "open"
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if line.startswith("status:"):
            status = line.split(":", 1)[1].strip()
            continue
        match = _SIG_HEADER.match(line)
        if match:
            signature = match.group(1)
    return signature, status
