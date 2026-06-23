"""Tuning result model + advisory config-diff markdown.

The report is **advisory**: like improvement proposals, it is never applied
automatically. A human reviews the suggested config diff and accepts it under
the standard quality gate. See AGENTS.md "Proposal Handling".
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path

from pydantic import BaseModel, Field

from harnesslab.tune.space import Config


class TrialRecord(BaseModel):
    config: dict
    cost: float
    breakdown: dict


class TuneReport(BaseModel):
    id: str
    status: str = "open"
    kind: str = "config_tuning"
    generated_at: datetime
    objective: str
    default_config: dict
    default_cost: float
    default_breakdown: dict
    best_config: dict
    best_cost: float
    best_breakdown: dict
    improved: bool
    trials: list[TrialRecord] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)


def make_report_id(best_config: Config, now: datetime) -> str:
    payload = ";".join(f"{k}={best_config[k]}" for k in sorted(best_config))
    sig8 = sha1(payload.encode("utf-8")).hexdigest()[:8]
    return f"tune_{now.strftime('%Y%m%d%H%M')}_{sig8}"


def build_report(
    *,
    objective: str,
    default_config: Config,
    default_breakdown: dict,
    best_config: Config,
    best_breakdown: dict,
    trials: list[TrialRecord],
    dimensions: list[str],
    now: datetime | None = None,
) -> TuneReport:
    now = now or datetime.now(UTC)
    default_cost = float(default_breakdown["cost"])
    best_cost = float(best_breakdown["cost"])
    return TuneReport(
        id=make_report_id(best_config, now),
        generated_at=now,
        objective=objective,
        default_config=dict(default_config),
        default_cost=default_cost,
        default_breakdown=dict(default_breakdown),
        best_config=dict(best_config),
        best_cost=best_cost,
        best_breakdown=dict(best_breakdown),
        improved=best_cost < default_cost,
        trials=trials,
        dimensions=list(dimensions),
    )


def render_report(report: TuneReport) -> str:
    lines: list[str] = []
    lines.append("---")
    lines.append(f"id: {report.id}")
    lines.append(f"status: {report.status}")
    lines.append(f"kind: {report.kind}")
    lines.append(f"generated_at: {report.generated_at.isoformat()}")
    lines.append(f"default_cost: {report.default_cost:.4f}")
    lines.append(f"best_cost: {report.best_cost:.4f}")
    lines.append(f"improved: {str(report.improved).lower()}")
    lines.append(f"trials: {len(report.trials)}")
    lines.append("---")
    lines.append("")
    lines.append("## Configuration tuning")
    lines.append("")
    lines.append(f"Objective: {report.objective}")
    lines.append("")
    if report.improved:
        lines.append(
            f"Best config lowers cost {report.default_cost:.4f} \u2192 "
            f"{report.best_cost:.4f} over {len(report.trials)} evaluation(s)."
        )
    else:
        lines.append(
            f"No configuration beat the default (cost {report.default_cost:.4f}) "
            f"over {len(report.trials)} evaluation(s). Default is retained."
        )
    lines.append("")

    lines.append("## Suggested config diff (advisory; not auto-applied)")
    lines.append("")
    lines.append("| Knob | Default | Suggested |")
    lines.append("| --- | --- | --- |")
    for key in report.dimensions:
        default_v = report.default_config.get(key)
        best_v = report.best_config.get(key)
        marker = "" if default_v == best_v else " **\u2190 change**"
        lines.append(f"| `{key}` | `{default_v}` | `{best_v}`{marker} |")
    lines.append("")

    lines.append("## Cost breakdown")
    lines.append("")
    lines.append("| Metric | Default | Best |")
    lines.append("| --- | --- | --- |")
    keys = ["cost", "failed_tasks", "tool_failures", "invalid_args", "denials", "tool_calls"]
    for k in keys:
        dv = report.default_breakdown.get(k)
        bv = report.best_breakdown.get(k)
        lines.append(f"| {k} | {dv} | {bv} |")
    lines.append("")

    lines.append("## Acceptance checklist")
    lines.append("")
    lines.append("- [ ] Reviewed by human")
    lines.append("- [ ] `uv run pytest` is green")
    lines.append("- [ ] `uv run harnesslab eval` shows no baseline regression")
    lines.append("- [ ] Config change applied via CLI/config (not hand-edited blindly)")
    lines.append("")
    return "\n".join(lines)


def write_report(report: TuneReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report.id}.md"
    path.write_text(render_report(report), encoding="utf-8")
    return path
