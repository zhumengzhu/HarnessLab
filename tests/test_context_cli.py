"""Phase 2.6 commit 2: harnesslab context CLI + metrics extension."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from harnesslab.cli import build_runtime
from harnesslab.core.models import TraceEvent
from harnesslab.replay.span_reader import read_spans
from harnesslab.telemetry.aggregate import aggregate, render_metrics
from harnesslab.telemetry.recorder_factory import default_spans_path


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


# ---------- end-to-end CLI smoke ----------


def _seed_spans_with_one_call(workspace: Path) -> Path:
    loop = build_runtime(workspace)
    session = loop.start(goal="cli context smoke")
    loop.run_turn(session.id, "hello")
    spans_path = default_spans_path(workspace)
    assert spans_path.exists()
    return spans_path


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", "-m", "harnesslab.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def test_context_show_prints_human_summary(tmp_path: Path) -> None:
    spans_path = _seed_spans_with_one_call(tmp_path)
    out = _run_cli("context", str(spans_path), "show", cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    body = out.stdout
    assert "ContextSnapshot summary" in body
    assert "model_calls_with_context: 1" in body
    assert "peak_usage_ratio" in body
    assert "latest:" in body
    assert "conversation_tokens:" in body


def test_context_show_json_mode_emits_machine_readable(tmp_path: Path) -> None:
    spans_path = _seed_spans_with_one_call(tmp_path)
    out = _run_cli("context", str(spans_path), "show", "--json", cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["model_calls_with_context"] == 1
    assert payload["latest"]["conversation_tokens"] > 0
    assert "usage_ratio" in payload["latest"]


def test_context_series_prints_one_row_per_call(tmp_path: Path) -> None:
    spans_path = _seed_spans_with_one_call(tmp_path)
    out = _run_cli("context", str(spans_path), "series", cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.strip().splitlines()
    # Header + separator + at least one data row.
    assert len(lines) >= 3
    assert "session" in lines[0]
    assert "conv_tok" in lines[0]


def test_context_show_handles_spans_with_no_snapshots(tmp_path: Path) -> None:
    spans_path = tmp_path / "bare.jsonl"
    end = datetime(2026, 5, 23, 22, 0, tzinfo=UTC)
    payload = {
        "resource": {},
        "trace_id": "t1",
        "span_id": "s1",
        "name": "llm.generate",
        "session_id": "s1",
        "turn_index": 0,
        "start_time": end.isoformat(),
        "end_time": end.isoformat(),
        "duration_ms": 1.2,
        "metrics": {"latency_ms": 1.2},
    }
    spans_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    out = _run_cli("context", str(spans_path), "show", cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    assert "(no llm.generate spans with context found)" in out.stdout


def test_context_show_session_filter_isolates_one_session(tmp_path: Path) -> None:
    """Two sessions share a trace; --session-id must restrict to one."""

    loop = build_runtime(tmp_path)
    s1 = loop.start(goal="alpha")
    loop.run_turn(s1.id, "first")
    s2 = loop.start(goal="beta")
    loop.run_turn(s2.id, "second")

    spans_path = default_spans_path(tmp_path)
    spans = read_spans(spans_path)
    s1_calls = [s for s in spans if s.name == "llm.generate" and s.session_id == s1.id]
    assert s1_calls, "fixture sanity"

    out = _run_cli(
        "context", str(spans_path), "show", "--session-id", s1.id, cwd=tmp_path
    )
    assert out.returncode == 0, out.stderr
    assert f"session_filter:           {s1.id}" in out.stdout
    assert "model_calls_with_context: 1" in out.stdout


def test_context_show_errors_on_missing_spans_path(tmp_path: Path) -> None:
    out = _run_cli("context", str(tmp_path / "nope.jsonl"), "show", cwd=tmp_path)
    assert out.returncode != 0
    assert "spans file not found" in (out.stderr + out.stdout)
