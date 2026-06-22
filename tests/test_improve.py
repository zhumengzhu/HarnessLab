"""Unit tests for the improvement-proposal subsystem (Step 6, Observability v2)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from harnesslab.core.models import SpanEventRecord, SpanRecord
from harnesslab.eval.task import TaskMetrics, TaskResult
from harnesslab.improve import (
    Proposal,
    build_clusters,
    dedupe_against_existing,
    fingerprint_for_eval_failure,
    fingerprint_for_span,
    generate,
    to_markdown,
    write_proposal,
)
from harnesslab.telemetry.span_attributes import HARNESSLAB_TOOL_NAME

_TS = datetime(2026, 1, 1, tzinfo=UTC)


def _span(
    *,
    name: str,
    session_id: str = "ses_demo",
    ok: bool | None = None,
    events: list[SpanEventRecord] | None = None,
    status_message: str | None = None,
) -> SpanRecord:
    attrs: dict = {HARNESSLAB_TOOL_NAME: name.split(".", 1)[-1]}
    if ok is not None:
        attrs["harnesslab.tool.ok"] = ok
    return SpanRecord(
        trace_id="t" * 32,
        span_id=f"span_{name}_{session_id}"[:16].ljust(16, "0"),
        name=name,
        session_id=session_id,
        turn_index=0,
        start_time=_TS,
        end_time=_TS,
        duration_ms=1.0,
        status="error" if ok is False else "ok",
        status_message=status_message,
        attributes=attrs,
        events=events or [],
    )


def _denied_span(tool: str, reason: str, session_id: str = "ses_demo") -> SpanRecord:
    return _span(
        name=f"tool.{tool}",
        session_id=session_id,
        ok=False,
        events=[
            SpanEventRecord(
                name="tool.policy_denied",
                time=_TS,
                attributes={"reason": reason},
            )
        ],
    )


def _invalid_args_span(tool: str, error: str, session_id: str = "ses_demo") -> SpanRecord:
    return _span(
        name=f"tool.{tool}",
        session_id=session_id,
        ok=False,
        events=[
            SpanEventRecord(
                name="tool.args_invalid",
                time=_TS,
                attributes={"error": error},
            )
        ],
    )


def _sample_failure_spans() -> list[SpanRecord]:
    """Span equivalents of ``fixtures/sample_failure_trace.jsonl``."""

    return [
        _denied_span("run_shell_safe", "command not in allowlist", "ses_demo_a"),
        _denied_span("run_shell_safe", "command not in allowlist", "ses_demo_a"),
        _invalid_args_span(
            "write_file", "'path' is a required property", "ses_demo_b"
        ),
        _invalid_args_span(
            "write_file", "'path' is a required property", "ses_demo_b"
        ),
    ]


# ---------- fingerprint ----------


def test_fingerprint_tool_executed_ok_returns_none() -> None:
    assert fingerprint_for_span(_span(name="tool.read_file", ok=True)) is None


def test_fingerprint_tool_executed_failure() -> None:
    fp = fingerprint_for_span(
        _span(
            name="tool.read_file",
            ok=False,
            status_message="[Errno 2] No such file or directory: '/x'",
        )
    )
    assert fp == (
        "tool_failure",
        "tool_executed:read_file:[Errno 2] No such file or directory: '/x'",
    )


def test_fingerprint_tool_denied() -> None:
    fp = fingerprint_for_span(
        _denied_span("run_shell_safe", "command not in allowlist")
    )
    assert fp == (
        "policy_denial",
        "tool_denied:run_shell_safe:command not in allowlist",
    )


def test_fingerprint_tool_invalid_args() -> None:
    fp = fingerprint_for_span(
        _invalid_args_span("write_file", "'path' is a required property")
    )
    assert fp == (
        "invalid_args",
        "tool_invalid_args:write_file:'path' is a required property",
    )


def test_fingerprint_non_failure_spans_return_none() -> None:
    for name in ("harnesslab.turn", "llm.generate", "harnesslab.step"):
        assert fingerprint_for_span(_span(name=name, ok=True)) is None


def test_fingerprint_truncates_long_reason() -> None:
    long_reason = "x" * 200
    fp = fingerprint_for_span(_denied_span("run_shell_safe", long_reason))
    assert fp is not None
    assert fp[1].endswith("…")
    assert len(fp[1].split(":", 2)[2]) <= 60


def test_fingerprint_for_eval_failure() -> None:
    kind, sig = fingerprint_for_eval_failure("write_then_read", "final reply missing")
    assert kind == "eval_regression"
    assert sig == "eval:write_then_read:final reply missing"


# ---------- cluster ----------


def test_build_clusters_filters_below_min_occurrences() -> None:
    spans = [_denied_span("run_shell_safe", "x")]
    assert build_clusters(spans, min_occurrences=2) == []


def test_build_clusters_groups_identical_signatures() -> None:
    spans = [_denied_span("run_shell_safe", "x")] * 3
    clusters = build_clusters(spans, min_occurrences=2)
    assert len(clusters) == 1
    assert clusters[0].occurrences == 3
    assert clusters[0].kind == "policy_denial"
    assert len(clusters[0].sample_spans) == 3


def test_build_clusters_sort_order_is_deterministic() -> None:
    spans = (
        [_denied_span("a", "x")] * 2
        + [_denied_span("b", "y")] * 5
    )
    clusters = build_clusters(spans, min_occurrences=2)
    assert [c.occurrences for c in clusters] == [5, 2]


def test_build_clusters_denominator_counts_tool_successes() -> None:
    # 2 failures of read_file out of 10 total invocations -> trials == 10.
    spans = (
        [_span(name="tool.read_file", ok=False, status_message="boom")] * 2
        + [_span(name="tool.read_file", ok=True)] * 8
    )
    clusters = build_clusters(spans, min_occurrences=2)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.occurrences == 2
    assert c.trials == 10
    assert c.posterior_failure_rate is not None
    # Posterior rate is well below the naive 2/2 == 1.0 point estimate.
    assert c.posterior_failure_rate < 0.5


def test_build_clusters_ranks_high_rate_rare_tool_above_low_rate_busy_tool() -> None:
    # alpha: 2/2 failures (100% observed). beta: 2/50 failures (4% observed).
    spans = (
        [_denied_span("alpha", "x")] * 2
        + [_denied_span("beta", "y")] * 2
        + [_span(name="tool.beta", ok=True)] * 48
    )
    clusters = build_clusters(spans, min_occurrences=2)
    assert len(clusters) == 2
    # The rare-but-always-failing tool must surface first (lower-confidence
    # bound ranking), even though both have the same occurrence count.
    assert clusters[0].signature == "tool_denied:alpha:x"
    assert clusters[1].signature == "tool_denied:beta:y"
    assert clusters[0].priority > clusters[1].priority


def test_build_clusters_includes_eval_failures() -> None:
    eval_results = [
        TaskResult(
            task_name="t1",
            passed=False,
            failures=["bad thing happened", "bad thing happened"],
            metrics=TaskMetrics(
                turns=1, tool_calls=0, tool_failures=0, denials=0, invalid_args=0
            ),
            final_reply="",
        )
    ]
    clusters = build_clusters([], eval_results=eval_results, min_occurrences=2)
    assert len(clusters) == 1
    assert clusters[0].kind == "eval_regression"
    assert clusters[0].occurrences == 2


def test_build_clusters_skips_passing_eval_results() -> None:
    eval_results = [
        TaskResult(
            task_name="t1",
            passed=True,
            failures=[],
            metrics=TaskMetrics(
                turns=1, tool_calls=0, tool_failures=0, denials=0, invalid_args=0
            ),
            final_reply="",
        )
    ]
    assert build_clusters([], eval_results=eval_results, min_occurrences=1) == []


# ---------- generate ----------


def _fixed_now() -> datetime:
    return datetime(2026, 5, 23, 22, 47, tzinfo=UTC)


def test_generate_proposal_id_is_stable_for_signature() -> None:
    spans = [_denied_span("x", "y")] * 2
    p1 = generate(spans, now=_fixed_now())[0]
    p2 = generate(spans, now=_fixed_now())[0]
    assert p1.id == p2.id


def test_generate_against_shipped_fixture() -> None:
    spans = _sample_failure_spans()
    proposals = generate(spans, now=_fixed_now())
    kinds = {p.kind for p in proposals}
    assert kinds == {"policy_denial", "invalid_args"}
    assert all(p.occurrences == 2 for p in proposals)
    for p in proposals:
        assert p.status == "open"
        assert p.suggested_actions
        assert p.related_files
        assert p.id.startswith("prop_202605232247_")


def test_generate_min_occurrences_threshold() -> None:
    spans = _sample_failure_spans()
    assert generate(spans, min_occurrences=3, now=_fixed_now()) == []


# ---------- dedupe ----------


def test_dedupe_returns_input_when_dir_missing(tmp_path: Path) -> None:
    proposals = generate(_sample_failure_spans(), now=_fixed_now())
    out = dedupe_against_existing(proposals, tmp_path / "does-not-exist")
    assert out == proposals


def test_dedupe_drops_signature_when_open_proposal_exists(tmp_path: Path) -> None:
    proposals = generate(_sample_failure_spans(), now=_fixed_now())
    for p in proposals:
        write_proposal(p, tmp_path)
    second = dedupe_against_existing(
        generate(_sample_failure_spans(), now=_fixed_now()),
        tmp_path,
    )
    assert second == []


def test_dedupe_ignores_accepted_proposals(tmp_path: Path) -> None:
    proposals = generate(_sample_failure_spans(), now=_fixed_now())
    for p in proposals:
        path = write_proposal(p, tmp_path)
        content = path.read_text(encoding="utf-8").replace(
            "status: open", "status: accepted", 1
        )
        path.write_text(content, encoding="utf-8")

    second = dedupe_against_existing(
        generate(_sample_failure_spans(), now=_fixed_now()),
        tmp_path,
    )
    assert {p.cluster_signature for p in second} == {
        p.cluster_signature for p in proposals
    }


def test_dedupe_ignores_unrelated_files_in_dir(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    proposals = generate(_sample_failure_spans(), now=_fixed_now())
    out = dedupe_against_existing(proposals, tmp_path)
    assert out == proposals


# ---------- render ----------


def _sample_proposal() -> Proposal:
    return generate(_sample_failure_spans(), now=_fixed_now())[0]


def test_to_markdown_contains_front_matter_and_checklist() -> None:
    md = to_markdown(_sample_proposal())
    assert md.startswith("---\n")
    assert "\nstatus: open\n" in md
    assert '\ncluster_signature: "' in md
    assert "## Suggested actions (advisory; not auto-applied)" in md
    assert "## Acceptance checklist" in md
    assert "uv run harnesslab eval" in md
    assert "uv run pytest" in md


def test_to_markdown_includes_sample_events_section() -> None:
    md = to_markdown(_sample_proposal())
    assert "## Sample events" in md
    assert "session=`ses_demo" in md


def test_generate_carries_posterior_fields_onto_proposal() -> None:
    spans = (
        [_span(name="tool.read_file", ok=False, status_message="boom")] * 2
        + [_span(name="tool.read_file", ok=True)] * 8
    )
    proposal = generate(spans, now=_fixed_now())[0]
    assert proposal.trials == 10
    assert proposal.posterior_failure_rate is not None
    assert proposal.credible_interval is not None
    assert proposal.priority is not None


def test_to_markdown_includes_posterior_failure_rate() -> None:
    spans = (
        [_span(name="tool.read_file", ok=False, status_message="boom")] * 2
        + [_span(name="tool.read_file", ok=True)] * 8
    )
    md = to_markdown(generate(spans, now=_fixed_now())[0])
    assert "posterior_failure_rate:" in md
    assert "Posterior failure rate" in md
    assert "90% CI" in md
    assert "2/10 observed" in md


def test_write_proposal_persists_file(tmp_path: Path) -> None:
    p = _sample_proposal()
    path = write_proposal(p, tmp_path / "nested")
    assert path.exists()
    assert path.name == f"{p.id}.md"
    content = path.read_text(encoding="utf-8")
    assert p.cluster_signature in content


# ---------- edge: empty inputs ----------


def test_generate_with_no_inputs_returns_empty() -> None:
    assert generate([], now=_fixed_now()) == []


def test_generate_with_only_successful_spans_returns_empty() -> None:
    spans = [_span(name="tool.read_file", ok=True)]
    assert generate(spans, now=_fixed_now()) == []


# ---------- defensive: malformed payload ----------


def test_fingerprint_handles_missing_payload_fields() -> None:
    fp = fingerprint_for_span(_span(name="tool.unknown", ok=False))
    assert fp == ("tool_failure", "tool_executed:unknown:")


# ---------- defensive: proposals_dir with malformed file ----------


def test_dedupe_skips_unreadable_proposal_files(tmp_path: Path) -> None:
    (tmp_path / "prop_garbage.md").write_text("no front matter here\n", encoding="utf-8")
    proposals = generate(_sample_failure_spans(), now=_fixed_now())
    out = dedupe_against_existing(proposals, tmp_path)
    assert out == proposals


# ---------- pydantic round-trip ----------


@pytest.mark.parametrize(
    "kind",
    ["tool_failure", "policy_denial", "invalid_args", "eval_regression"],
)
def test_proposal_json_round_trip(kind: str) -> None:
    p = Proposal(
        id="prop_x",
        kind=kind,
        cluster_signature="x:y:z",
        occurrences=2,
        generated_at=_fixed_now(),
        suggested_actions=["a", "b"],
    )
    restored = Proposal.model_validate_json(p.model_dump_json())
    assert restored == p
