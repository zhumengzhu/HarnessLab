"""Baseline persistence + regression comparison."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from harnesslab.eval.task import TaskMetrics, TaskResult


class BaselineEntry(BaseModel):
    passed: bool
    metrics: TaskMetrics


class Baseline(BaseModel):
    version: int = 1
    results: dict[str, BaselineEntry]


@dataclass(frozen=True)
class Regression:
    task_name: str
    kind: str
    detail: str


def load_baseline(path: Path) -> Baseline | None:
    if not path.exists():
        return None
    return Baseline.model_validate_json(path.read_text(encoding="utf-8"))


def save_baseline(path: Path, results: list[TaskResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline = Baseline(
        results={
            r.task_name: BaselineEntry(passed=r.passed, metrics=r.metrics)
            for r in results
        }
    )
    payload = baseline.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def compare(results: list[TaskResult], baseline: Baseline | None) -> list[Regression]:
    """Detect regressions of the current run against the baseline.

    Regressions:
      - a task that was passing in baseline is now failing
      - tool_failures or invalid_args count increased
    Other metric movements (e.g. tool_calls going up because the agent
    explored more) are informational, not regressions.
    """

    if baseline is None:
        return []
    regressions: list[Regression] = []
    for r in results:
        b = baseline.results.get(r.task_name)
        if b is None:
            continue
        if b.passed and not r.passed:
            regressions.append(
                Regression(
                    task_name=r.task_name,
                    kind="task_now_failing",
                    detail=(
                        "was passing in baseline, now failing: "
                        + "; ".join(r.failures)
                    ),
                )
            )
        if r.metrics.tool_failures > b.metrics.tool_failures:
            regressions.append(
                Regression(
                    task_name=r.task_name,
                    kind="tool_failures_increased",
                    detail=(
                        f"tool_failures {b.metrics.tool_failures} -> "
                        f"{r.metrics.tool_failures}"
                    ),
                )
            )
        if r.metrics.invalid_args > b.metrics.invalid_args:
            regressions.append(
                Regression(
                    task_name=r.task_name,
                    kind="invalid_args_increased",
                    detail=(
                        f"invalid_args {b.metrics.invalid_args} -> "
                        f"{r.metrics.invalid_args}"
                    ),
                )
            )
    return regressions
