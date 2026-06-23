"""Advisory ``prompt_tuning`` proposal model + markdown render.

Like every proposal in this project, the output is **advisory**: a human
reviews the suggested prompt and accepts it under the standard quality gate.
The candidates were LLM-generated and frozen; the ranking comes from an
isolated live-model benchmark. Nothing here is auto-applied. See AGENTS.md
"Proposal Handling" §5 (amendment).
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path

from pydantic import BaseModel, Field

from harnesslab.tune.prompt.selection import CandidateRanking

_PROMPT_PREVIEW_CHARS = 600


class RankingRecord(BaseModel):
    candidate_id: str
    label: str
    source: str
    passes: int
    trials: int
    success_rate: float
    low: float
    high: float


class PromptTuneReport(BaseModel):
    id: str
    status: str = "open"
    kind: str = "prompt_tuning"
    generated_at: datetime
    instruction: str
    repeats: int
    benchmark_tasks: int
    improved: bool
    baseline_id: str
    best_id: str
    best_prompt: str
    rankings: list[RankingRecord] = Field(default_factory=list)


def make_report_id(best_id: str, now: datetime) -> str:
    sig8 = sha1(best_id.encode("utf-8")).hexdigest()[:8]
    return f"prompt_{now.strftime('%Y%m%d%H%M')}_{sig8}"


def _to_record(r: CandidateRanking) -> RankingRecord:
    return RankingRecord(
        candidate_id=r.candidate.id,
        label=r.candidate.label,
        source=r.candidate.source,
        passes=r.result.passes,
        trials=r.result.trials,
        success_rate=r.success_rate,
        low=r.low,
        high=r.high,
    )


def build_prompt_report(
    *,
    rankings: list[CandidateRanking],
    baseline_id: str,
    instruction: str,
    repeats: int,
    benchmark_tasks: int,
    now: datetime | None = None,
) -> PromptTuneReport:
    if not rankings:
        raise ValueError("cannot build a report from an empty ranking")
    now = now or datetime.now(UTC)
    best = rankings[0]
    baseline = next(
        (r for r in rankings if r.candidate.id == baseline_id), rankings[-1]
    )
    improved = best.candidate.id != baseline.candidate.id and best.low > baseline.low
    return PromptTuneReport(
        id=make_report_id(best.candidate.id, now),
        generated_at=now,
        instruction=instruction,
        repeats=repeats,
        benchmark_tasks=benchmark_tasks,
        improved=improved,
        baseline_id=baseline.candidate.id,
        best_id=best.candidate.id,
        best_prompt=best.candidate.system_prompt,
        rankings=[_to_record(r) for r in rankings],
    )


def render_prompt_report(report: PromptTuneReport) -> str:
    lines: list[str] = []
    lines.append("---")
    lines.append(f"id: {report.id}")
    lines.append(f"status: {report.status}")
    lines.append(f"kind: {report.kind}")
    lines.append(f"generated_at: {report.generated_at.isoformat()}")
    lines.append(f"improved: {str(report.improved).lower()}")
    lines.append(f"baseline_id: {report.baseline_id}")
    lines.append(f"best_id: {report.best_id}")
    lines.append(f"repeats: {report.repeats}")
    lines.append(f"benchmark_tasks: {report.benchmark_tasks}")
    lines.append("---")
    lines.append("")
    lines.append("## Prompt tuning (advisory; not auto-applied)")
    lines.append("")
    if report.instruction:
        lines.append(f"Instruction: {report.instruction}")
        lines.append("")
    baseline = next(
        (r for r in report.rankings if r.candidate_id == report.baseline_id), None
    )
    best = next(
        (r for r in report.rankings if r.candidate_id == report.best_id), None
    )
    if report.improved and baseline and best:
        lines.append(
            f"Best candidate `{best.candidate_id}` raises the benchmark "
            f"success-rate lower bound {baseline.low:.3f} \u2192 {best.low:.3f} "
            f"(mean {baseline.success_rate:.3f} \u2192 {best.success_rate:.3f})."
        )
    else:
        lines.append(
            "No candidate beat the baseline on the success-rate lower bound. "
            "Baseline prompt is retained."
        )
    lines.append("")
    lines.append(
        "Scores come from a live-model benchmark isolated from `eval`/`replay`; "
        "they are non-deterministic. Re-run with more `--repeats` before trusting "
        "a narrow margin."
    )
    lines.append("")

    lines.append("## Candidate ranking")
    lines.append("")
    lines.append("| Rank | Candidate | Source | Pass/Trials | Success (mean) | LCB | UCB |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for i, r in enumerate(report.rankings, start=1):
        tag = ""
        if r.candidate_id == report.best_id:
            tag = " **\u2190 best**"
        elif r.candidate_id == report.baseline_id:
            tag = " (baseline)"
        label = f"`{r.candidate_id}`{tag}"
        lines.append(
            f"| {i} | {label} | {r.source} | {r.passes}/{r.trials} | "
            f"{r.success_rate:.3f} | {r.low:.3f} | {r.high:.3f} |"
        )
    lines.append("")

    lines.append("## Suggested prompt")
    lines.append("")
    preview = report.best_prompt.strip()
    truncated = len(preview) > _PROMPT_PREVIEW_CHARS
    if truncated:
        preview = preview[:_PROMPT_PREVIEW_CHARS].rstrip() + "\n…(truncated)"
    lines.append("```text")
    lines.append(preview)
    lines.append("```")
    lines.append("")

    lines.append("## Acceptance checklist")
    lines.append("")
    lines.append("- [ ] Reviewed by human")
    lines.append("- [ ] Benchmark margin re-confirmed with higher `--repeats`")
    lines.append("- [ ] `uv run pytest` is green")
    lines.append("- [ ] `uv run harnesslab eval` shows no baseline regression")
    lines.append("- [ ] Prompt change applied via prompt blocks (not hand-edited blindly)")
    lines.append("")
    return "\n".join(lines)


def write_prompt_report(report: PromptTuneReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report.id}.md"
    path.write_text(render_prompt_report(report), encoding="utf-8")
    return path
