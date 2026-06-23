"""Tests for the advisory tuning report rendering (Layer B1)."""

from __future__ import annotations

from datetime import UTC, datetime

from harnesslab.tune.report import TrialRecord, build_report, render_report

_NOW = datetime(2026, 6, 22, 23, 30, tzinfo=UTC)
_DIMS = ["shell_profile", "output_bytes_cap"]


def _breakdown(cost: float, **kw: int) -> dict:
    base = {
        "cost": cost,
        "failed_tasks": 0,
        "tool_failures": 0,
        "invalid_args": 0,
        "denials": 0,
        "tool_calls": 0,
    }
    base.update(kw)
    return base


def test_report_marks_improvement_and_changed_knob() -> None:
    report = build_report(
        objective="minimize cost",
        default_config={"shell_profile": "dev", "output_bytes_cap": 65536},
        default_breakdown=_breakdown(110.0, failed_tasks=1, tool_calls=100),
        best_config={"shell_profile": "dev", "output_bytes_cap": 131072},
        best_breakdown=_breakdown(10.0, tool_calls=100),
        trials=[
            TrialRecord(
                config={"shell_profile": "dev", "output_bytes_cap": 65536},
                cost=110.0,
                breakdown=_breakdown(110.0, failed_tasks=1, tool_calls=100),
            )
        ],
        dimensions=_DIMS,
        now=_NOW,
    )
    assert report.improved is True
    md = render_report(report)
    assert md.startswith("---\n")
    assert "kind: config_tuning" in md
    assert "## Suggested config diff (advisory; not auto-applied)" in md
    assert "\u2190 change" in md  # output_bytes_cap changed
    assert "## Acceptance checklist" in md
    assert "lowers cost" in md


def test_report_states_no_improvement_when_default_is_best() -> None:
    bd = _breakdown(0.0)
    report = build_report(
        objective="minimize cost",
        default_config={"shell_profile": "dev", "output_bytes_cap": 65536},
        default_breakdown=bd,
        best_config={"shell_profile": "dev", "output_bytes_cap": 65536},
        best_breakdown=bd,
        trials=[],
        dimensions=_DIMS,
        now=_NOW,
    )
    assert report.improved is False
    md = render_report(report)
    assert "No configuration beat the default" in md


def test_report_id_is_stable_for_config_and_time() -> None:
    args = dict(
        objective="x",
        default_config={"shell_profile": "dev", "output_bytes_cap": 65536},
        default_breakdown=_breakdown(1.0),
        best_config={"shell_profile": "strict", "output_bytes_cap": 16384},
        best_breakdown=_breakdown(0.0),
        trials=[],
        dimensions=_DIMS,
        now=_NOW,
    )
    a = build_report(**args)
    b = build_report(**args)
    assert a.id == b.id
    assert a.id.startswith("tune_202606222330_")
