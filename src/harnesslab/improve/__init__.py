"""HarnessLab improvement-proposal subsystem (Step 6).

Public API:
    fingerprint_for_span(span)              -> (kind, signature) | None
    fingerprint_for_eval_failure(name, msg) -> (kind, signature)
    build_clusters(spans, eval_results, min_occurrences=2) -> list[Cluster]
    generate(spans, eval_results, min_occurrences, now=None) -> list[Proposal]
    dedupe_against_existing(proposals, proposals_dir) -> list[Proposal]
    to_markdown(proposal) -> str
    write_proposal(proposal, out_dir) -> Path

Generated proposals are ADVISORY. See AGENTS.md "Proposal Handling".
"""

from harnesslab.improve.cluster import Cluster, build_clusters
from harnesslab.improve.fingerprint import (
    fingerprint_for_eval_failure,
    fingerprint_for_span,
)
from harnesslab.improve.generator import dedupe_against_existing, generate
from harnesslab.improve.proposal import Proposal, ProposalStatus
from harnesslab.improve.render import to_markdown, write_proposal

__all__ = [
    "Cluster",
    "Proposal",
    "ProposalStatus",
    "build_clusters",
    "dedupe_against_existing",
    "fingerprint_for_eval_failure",
    "fingerprint_for_span",
    "generate",
    "to_markdown",
    "write_proposal",
]
