"""Report rendering for eval results: stdout summary + JSON artifact."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from harnesslab.eval.baseline import Regression
from harnesslab.eval.task import TaskResult


def render_stdout(results: list[TaskResult], regressions: list[Regression]) -> str:
    lines: list[str] = []
    for r in results:
        symbol = "PASS" if r.passed else "FAIL"
        lines.append(f"[{symbol}] {r.task_name}")
        for failure in r.failures:
            lines.append(f"    - {failure}")
        lines.append(
            "    metrics: "
            f"turns={r.metrics.turns} "
            f"tool_calls={r.metrics.tool_calls} "
            f"tool_failures={r.metrics.tool_failures} "
            f"denials={r.metrics.denials} "
            f"invalid_args={r.metrics.invalid_args}"
        )

    if regressions:
        lines.append("")
        lines.append("REGRESSIONS:")
        for reg in regressions:
            lines.append(f"  - [{reg.task_name}] {reg.kind}: {reg.detail}")

    pass_count = sum(1 for r in results if r.passed)
    lines.append("")
    lines.append(
        f"Summary: {pass_count}/{len(results)} passed, "
        f"{len(regressions)} regressions"
    )
    return "\n".join(lines)


def write_json(
    path: Path,
    results: list[TaskResult],
    regressions: list[Regression],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "results": [r.model_dump(mode="json") for r in results],
        "regressions": [asdict(reg) for reg in regressions],
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
