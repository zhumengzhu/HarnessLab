"""Render a Proposal to markdown and write it to disk."""

from __future__ import annotations

import json
from pathlib import Path

from harnesslab.improve.proposal import Proposal

_SAMPLE_PAYLOAD_PREVIEW = 200


def to_markdown(proposal: Proposal) -> str:
    """Render the proposal as front-matter + body markdown."""

    lines: list[str] = []
    lines.append("---")
    lines.append(f"id: {proposal.id}")
    lines.append(f"status: {proposal.status}")
    lines.append(f"kind: {proposal.kind}")
    lines.append(f'cluster_signature: "{proposal.cluster_signature}"')
    lines.append(f"occurrences: {proposal.occurrences}")
    lines.append(f"generated_at: {proposal.generated_at.isoformat()}")
    if proposal.related_files:
        lines.append("related_files:")
        for f in proposal.related_files:
            lines.append(f"  - {f}")
    lines.append("---")
    lines.append("")
    lines.append("## Cluster")
    lines.append("")
    lines.append(
        f"{proposal.occurrences} occurrence(s) of signature "
        f"`{proposal.cluster_signature}`."
    )
    lines.append("")

    if proposal.sample_events:
        lines.append("## Sample events")
        lines.append("")
        for event in proposal.sample_events:
            payload = json.dumps(event.get("payload", {}), ensure_ascii=False)
            if len(payload) > _SAMPLE_PAYLOAD_PREVIEW:
                payload = payload[: _SAMPLE_PAYLOAD_PREVIEW - 1] + "…"
            lines.append(
                f"- `{event.get('event_type')}` "
                f"session=`{event.get('session_id')}` "
                f"payload=`{payload}`"
            )
        lines.append("")

    if proposal.sample_task_failures:
        lines.append("## Sample task failures")
        lines.append("")
        for task_name, failure in proposal.sample_task_failures:
            lines.append(f"- `{task_name}`: {failure}")
        lines.append("")

    lines.append("## Suggested actions (advisory; not auto-applied)")
    lines.append("")
    for i, action in enumerate(proposal.suggested_actions, 1):
        lines.append(f"{i}. {action}")
    lines.append("")

    lines.append("## Acceptance checklist")
    lines.append("")
    lines.append("- [ ] Reviewed by human")
    lines.append("- [ ] `uv run pytest` is green")
    lines.append("- [ ] `uv run harnesslab eval` shows no baseline regression")
    lines.append("- [ ] If code changed, a test was added or updated")
    lines.append("")

    return "\n".join(lines)


def write_proposal(proposal: Proposal, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{proposal.id}.md"
    path.write_text(to_markdown(proposal), encoding="utf-8")
    return path
