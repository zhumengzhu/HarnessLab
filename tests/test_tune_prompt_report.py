"""Tests for the advisory prompt_tuning report."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from harnesslab.tune.prompt.benchmark import BenchmarkResult
from harnesslab.tune.prompt.candidate import PromptCandidate, baseline_candidate
from harnesslab.tune.prompt.report import (
    build_prompt_report,
    render_prompt_report,
    write_prompt_report,
)
from harnesslab.tune.prompt.selection import rank_candidates

_NOW = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)


def _rankings(baseline_pass: int, cand_pass: int):
    baseline = baseline_candidate()
    cand = PromptCandidate.from_text("GOOD candidate prompt")
    return (
        baseline,
        rank_candidates(
            [
                (baseline, BenchmarkResult(baseline.id, baseline_pass, 5)),
                (cand, BenchmarkResult(cand.id, cand_pass, 5)),
            ]
        ),
    )


def test_report_marks_improvement() -> None:
    baseline, rankings = _rankings(baseline_pass=1, cand_pass=5)
    report = build_prompt_report(
        rankings=rankings,
        baseline_id=baseline.id,
        instruction="be concise",
        repeats=1,
        benchmark_tasks=5,
        now=_NOW,
    )
    assert report.improved
    assert report.best_id != baseline.id
    assert report.id.startswith("prompt_")


def test_report_no_improvement_when_baseline_best() -> None:
    baseline, rankings = _rankings(baseline_pass=5, cand_pass=0)
    report = build_prompt_report(
        rankings=rankings,
        baseline_id=baseline.id,
        instruction="",
        repeats=1,
        benchmark_tasks=5,
        now=_NOW,
    )
    assert not report.improved
    assert report.best_id == baseline.id


def test_render_contains_advisory_markers() -> None:
    baseline, rankings = _rankings(baseline_pass=1, cand_pass=5)
    report = build_prompt_report(
        rankings=rankings,
        baseline_id=baseline.id,
        instruction="be concise",
        repeats=2,
        benchmark_tasks=5,
        now=_NOW,
    )
    md = render_prompt_report(report)
    assert "kind: prompt_tuning" in md
    assert "advisory; not auto-applied" in md
    assert "\u2190 best" in md
    assert "Acceptance checklist" in md
    assert "isolated from `eval`/`replay`" in md


def test_write_prompt_report_creates_file(tmp_path: Path) -> None:
    baseline, rankings = _rankings(baseline_pass=1, cand_pass=5)
    report = build_prompt_report(
        rankings=rankings,
        baseline_id=baseline.id,
        instruction="",
        repeats=1,
        benchmark_tasks=5,
        now=_NOW,
    )
    path = write_prompt_report(report, tmp_path / "props")
    assert path.exists()
    assert path.name == f"{report.id}.md"
