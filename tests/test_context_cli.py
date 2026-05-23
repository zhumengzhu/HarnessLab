"""Phase 2.6 commit 2: harnesslab context CLI + metrics extension."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from harnesslab.cli import build_runtime
from harnesslab.core.models import TraceEvent
from harnesslab.replay import read_trace
from harnesslab.telemetry.aggregate import aggregate, render_metrics


def _evt(
    et: str,
    payload: dict,
    *,
    session_id: str = "s_a",
    when: datetime | None = None,
) -> TraceEvent:
    return TraceEvent(
        run_id=session_id,
        session_id=session_id,
        event_type=et,
        payload=payload,
        created_at=when or datetime.now(UTC),
    )


# ---------- metrics aggregation now includes context fields ----------


def test_aggregate_records_peak_conversation_and_usage_from_model_calls() -> None:
    events = [
        _evt(
            "model_call",
            {
                "context": {
                    "conversation_tokens": 120,
                    "message_count": 5,
                    "limit_tokens": 1000,
                    "compaction_threshold_tokens": 800,
                    "usage_ratio": 0.12,
                    "threshold_ratio": 0.15,
                },
            },
        ),
        _evt(
            "model_call",
            {
                "context": {
                    "conversation_tokens": 450,
                    "message_count": 12,
                    "limit_tokens": 1000,
                    "compaction_threshold_tokens": 800,
                    "usage_ratio": 0.45,
                    "threshold_ratio": 0.5625,
                },
            },
        ),
        _evt("compaction_started", {"trigger": "threshold"}),
        _evt("compaction_started", {"trigger": "overflow"}),
    ]
    m = aggregate(events)
    assert m.max_conversation_tokens == 450
    assert m.peak_usage_ratio == 0.45
    assert m.compactions == 2
    assert m.overflow_recoveries == 1


def test_aggregate_defaults_context_fields_for_pre_phase26_traces() -> None:
    """A trace without ``context`` payload still aggregates cleanly."""

    events = [_evt("model_call", {"latency_ms": 1.0})]
    m = aggregate(events)
    assert m.max_conversation_tokens == 0
    assert m.peak_usage_ratio is None
    assert m.compactions == 0
    assert m.overflow_recoveries == 0


def test_render_metrics_mentions_context_line() -> None:
    events = [
        _evt("model_call", {"context": {
            "conversation_tokens": 10, "message_count": 1,
            "limit_tokens": 100, "compaction_threshold_tokens": 80,
            "usage_ratio": 0.1, "threshold_ratio": 0.125,
        }}),
    ]
    out = render_metrics(aggregate(events))
    assert "context:" in out
    assert "max_tokens=10" in out
    assert "compactions=0" in out
    assert "overflow_recoveries=0" in out


# ---------- collect_context_snapshots helper ----------


def test_collect_context_snapshots_filters_by_session_and_orders_by_time(
    tmp_path: Path,
) -> None:
    from harnesslab.cli import _collect_context_snapshots

    base = datetime(2026, 5, 23, 10, 0, tzinfo=UTC)
    events = [
        _evt(
            "model_call",
            {"context": {
                "conversation_tokens": 50, "message_count": 2,
                "limit_tokens": 1000, "compaction_threshold_tokens": 800,
                "usage_ratio": 0.05, "threshold_ratio": 0.0625,
            }},
            session_id="s_a",
            when=base,
        ),
        _evt(
            "model_call",
            {"context": {
                "conversation_tokens": 99, "message_count": 3,
                "limit_tokens": 1000, "compaction_threshold_tokens": 800,
                "usage_ratio": 0.099, "threshold_ratio": 0.124,
            }},
            session_id="s_b",
            when=base.replace(minute=1),
        ),
        _evt(
            "model_call",
            {"context": {
                "conversation_tokens": 75, "message_count": 4,
                "limit_tokens": 1000, "compaction_threshold_tokens": 800,
                "usage_ratio": 0.075, "threshold_ratio": 0.09375,
            }},
            session_id="s_a",
            when=base.replace(minute=2),
        ),
    ]
    rows = _collect_context_snapshots(events, session_id="s_a")
    assert [r["conversation_tokens"] for r in rows] == [50, 75]

    all_rows = _collect_context_snapshots(events, session_id=None)
    assert len(all_rows) == 3
    assert all_rows == sorted(all_rows, key=lambda r: r["created_at"])


def test_collect_context_snapshots_skips_model_calls_without_context() -> None:
    from harnesslab.cli import _collect_context_snapshots

    events = [
        _evt("model_call", {"latency_ms": 1.0}),
        _evt(
            "model_call",
            {"context": {
                "conversation_tokens": 5, "message_count": 1,
                "limit_tokens": 100, "compaction_threshold_tokens": 80,
                "usage_ratio": 0.05, "threshold_ratio": 0.0625,
            }},
        ),
    ]
    rows = _collect_context_snapshots(events, session_id=None)
    assert len(rows) == 1
    assert rows[0]["conversation_tokens"] == 5


# ---------- end-to-end CLI smoke ----------


def _seed_trace_with_one_call(workspace: Path) -> Path:
    loop = build_runtime(workspace)
    session = loop.start(goal="cli context smoke")
    loop.run_turn(session.id, "hello")
    trace_path = workspace / ".harnesslab" / "trace.jsonl"
    assert trace_path.exists()
    return trace_path


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", "-m", "harnesslab.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def test_context_show_prints_human_summary(tmp_path: Path) -> None:
    trace_path = _seed_trace_with_one_call(tmp_path)
    out = _run_cli("context", str(trace_path), "show", cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    body = out.stdout
    assert "ContextSnapshot summary" in body
    assert "model_calls_with_context: 1" in body
    assert "peak_usage_ratio" in body
    assert "latest:" in body
    assert "conversation_tokens:" in body


def test_context_show_json_mode_emits_machine_readable(tmp_path: Path) -> None:
    trace_path = _seed_trace_with_one_call(tmp_path)
    out = _run_cli("context", str(trace_path), "show", "--json", cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["model_calls_with_context"] == 1
    assert payload["latest"]["conversation_tokens"] > 0
    assert "usage_ratio" in payload["latest"]


def test_context_series_prints_one_row_per_call(tmp_path: Path) -> None:
    trace_path = _seed_trace_with_one_call(tmp_path)
    out = _run_cli("context", str(trace_path), "series", cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.strip().splitlines()
    # Header + separator + at least one data row.
    assert len(lines) >= 3
    assert "session" in lines[0]
    assert "conv_tok" in lines[0]


def test_context_show_handles_trace_with_no_snapshots(tmp_path: Path) -> None:
    # Hand-write a trace with model_call but no context block.
    trace_path = tmp_path / "bare.jsonl"
    payload = {
        "run_id": "r1", "session_id": "s1", "event_type": "model_call",
        "payload": {"latency_ms": 1.2}, "created_at": "2026-05-23T22:00:00+00:00",
    }
    trace_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    out = _run_cli("context", str(trace_path), "show", cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    assert "(no model_call events with context found)" in out.stdout


def test_context_show_session_filter_isolates_one_session(tmp_path: Path) -> None:
    """Two sessions share a trace; --session-id must restrict to one."""

    loop = build_runtime(tmp_path)
    s1 = loop.start(goal="alpha")
    loop.run_turn(s1.id, "first")
    s2 = loop.start(goal="beta")
    loop.run_turn(s2.id, "second")

    trace_path = tmp_path / ".harnesslab" / "trace.jsonl"
    events = read_trace(trace_path)
    s1_calls = [
        e for e in events
        if e.event_type == "model_call" and e.session_id == s1.id
    ]
    assert s1_calls, "fixture sanity"

    out = _run_cli(
        "context", str(trace_path), "show", "--session-id", s1.id, cwd=tmp_path
    )
    assert out.returncode == 0, out.stderr
    assert f"session_filter:           {s1.id}" in out.stdout
    assert "model_calls_with_context: 1" in out.stdout


def test_context_show_errors_on_missing_trace_path(tmp_path: Path) -> None:
    out = _run_cli("context", str(tmp_path / "nope.jsonl"), "show", cwd=tmp_path)
    assert out.returncode != 0
    assert "trace file not found" in (out.stderr + out.stdout)
