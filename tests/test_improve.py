"""Unit tests for the improvement-proposal subsystem (Step 6)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from harnesslab.core.models import TraceEvent
from harnesslab.eval.task import TaskMetrics, TaskResult
from harnesslab.improve import (
    Proposal,
    build_clusters,
    dedupe_against_existing,
    fingerprint_for_eval_failure,
    fingerprint_for_event,
    generate,
    to_markdown,
    write_proposal,
)
from harnesslab.replay import read_trace

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_failure_trace.jsonl"


# ---------- fingerprint ----------


def _evt(event_type: str, payload: dict | None = None) -> TraceEvent:
    return TraceEvent(
        run_id="r",
        session_id="r",
        event_type=event_type,
        payload=payload or {},
    )


def test_fingerprint_tool_executed_ok_returns_none() -> None:
    assert (
        fingerprint_for_event(
            _evt("tool_executed", {"tool": "read_file", "ok": True})
        )
        is None
    )


def test_fingerprint_tool_executed_failure() -> None:
    fp = fingerprint_for_event(
        _evt(
            "tool_executed",
            {
                "tool": "read_file",
                "ok": False,
                "error": "[Errno 2] No such file or directory: '/x'",
            },
        )
    )
    assert fp == (
        "tool_failure",
        "tool_executed:read_file:[Errno 2] No such file or directory: '/x'",
    )


def test_fingerprint_tool_denied() -> None:
    fp = fingerprint_for_event(
        _evt(
            "tool_denied",
            {"tool": "run_shell_safe", "reason": "command not in allowlist"},
        )
    )
    assert fp == (
        "policy_denial",
        "tool_denied:run_shell_safe:command not in allowlist",
    )


def test_fingerprint_tool_invalid_args() -> None:
    fp = fingerprint_for_event(
        _evt(
            "tool_invalid_args",
            {"tool": "write_file", "error": "'path' is a required property"},
        )
    )
    assert fp == (
        "invalid_args",
        "tool_invalid_args:write_file:'path' is a required property",
    )


def test_fingerprint_non_failure_events_return_none() -> None:
    for et in ("session_started", "user_input_received", "decision_made"):
        assert fingerprint_for_event(_evt(et, {})) is None


def test_fingerprint_truncates_long_reason() -> None:
    long_reason = "x" * 200
    fp = fingerprint_for_event(
        _evt("tool_denied", {"tool": "run_shell_safe", "reason": long_reason})
    )
    assert fp is not None
    assert fp[1].endswith("…")
    assert len(fp[1].split(":", 2)[2]) <= 60


def test_fingerprint_for_eval_failure() -> None:
    kind, sig = fingerprint_for_eval_failure("write_then_read", "final reply missing")
    assert kind == "eval_regression"
    assert sig == "eval:write_then_read:final reply missing"


# ---------- cluster ----------


def test_build_clusters_filters_below_min_occurrences() -> None:
    events = [
        _evt("tool_denied", {"tool": "run_shell_safe", "reason": "x"}),
    ]
    assert build_clusters(events, min_occurrences=2) == []


def test_build_clusters_groups_identical_signatures() -> None:
    events = [
        _evt("tool_denied", {"tool": "run_shell_safe", "reason": "x"}),
        _evt("tool_denied", {"tool": "run_shell_safe", "reason": "x"}),
        _evt("tool_denied", {"tool": "run_shell_safe", "reason": "x"}),
    ]
    clusters = build_clusters(events, min_occurrences=2)
    assert len(clusters) == 1
    assert clusters[0].occurrences == 3
    assert clusters[0].kind == "policy_denial"
    assert len(clusters[0].sample_events) == 3  # cap is 3


def test_build_clusters_sort_order_is_deterministic() -> None:
    events = (
        [_evt("tool_denied", {"tool": "a", "reason": "x"})] * 2
        + [_evt("tool_denied", {"tool": "b", "reason": "y"})] * 5
    )
    clusters = build_clusters(events, min_occurrences=2)
    assert [c.occurrences for c in clusters] == [5, 2]


def test_build_clusters_includes_eval_failures() -> None:
    events = []
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
    clusters = build_clusters(events, eval_results=eval_results, min_occurrences=2)
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
    events = [_evt("tool_denied", {"tool": "x", "reason": "y"})] * 2
    p1 = generate(events, now=_fixed_now())[0]
    p2 = generate(events, now=_fixed_now())[0]
    assert p1.id == p2.id


def test_generate_against_shipped_fixture() -> None:
    events = read_trace(FIXTURE)
    proposals = generate(events, now=_fixed_now())
    kinds = {p.kind for p in proposals}
    assert kinds == {"policy_denial", "invalid_args"}
    assert all(p.occurrences == 2 for p in proposals)
    for p in proposals:
        assert p.status == "open"
        assert p.suggested_actions  # templates returned non-empty
        assert p.related_files  # template hints attached
        assert p.id.startswith("prop_202605232247_")


def test_generate_min_occurrences_threshold() -> None:
    events = read_trace(FIXTURE)
    assert generate(events, min_occurrences=3, now=_fixed_now()) == []


# ---------- dedupe ----------


def test_dedupe_returns_input_when_dir_missing(tmp_path: Path) -> None:
    proposals = generate(read_trace(FIXTURE), now=_fixed_now())
    out = dedupe_against_existing(proposals, tmp_path / "does-not-exist")
    assert out == proposals


def test_dedupe_drops_signature_when_open_proposal_exists(tmp_path: Path) -> None:
    proposals = generate(read_trace(FIXTURE), now=_fixed_now())
    # Persist all proposals to disk so signatures are "open".
    for p in proposals:
        write_proposal(p, tmp_path)
    # Second run should yield zero new proposals.
    second = dedupe_against_existing(
        generate(read_trace(FIXTURE), now=_fixed_now()),
        tmp_path,
    )
    assert second == []


def test_dedupe_ignores_accepted_proposals(tmp_path: Path) -> None:
    proposals = generate(read_trace(FIXTURE), now=_fixed_now())
    for p in proposals:
        path = write_proposal(p, tmp_path)
        # Flip status to accepted in the file.
        content = path.read_text(encoding="utf-8").replace(
            "status: open", "status: accepted", 1
        )
        path.write_text(content, encoding="utf-8")

    second = dedupe_against_existing(
        generate(read_trace(FIXTURE), now=_fixed_now()),
        tmp_path,
    )
    # Accepted proposals don't block re-emission.
    assert {p.cluster_signature for p in second} == {
        p.cluster_signature for p in proposals
    }


def test_dedupe_ignores_unrelated_files_in_dir(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    proposals = generate(read_trace(FIXTURE), now=_fixed_now())
    out = dedupe_against_existing(proposals, tmp_path)
    assert out == proposals  # README.md is not a proposal


# ---------- render ----------


def _sample_proposal() -> Proposal:
    return generate(read_trace(FIXTURE), now=_fixed_now())[0]


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
    assert "session=`ses_demo" in md  # sessions from the fixture appear


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


def test_generate_with_only_successful_events_returns_empty() -> None:
    events = [
        _evt("tool_executed", {"tool": "read_file", "ok": True}),
        _evt("session_started", {"goal": "x"}),
    ]
    assert generate(events, now=_fixed_now()) == []


# ---------- defensive: malformed payload ----------


def test_fingerprint_handles_missing_payload_fields() -> None:
    # No 'tool', no 'error': fingerprint still computes a stable key.
    fp = fingerprint_for_event(_evt("tool_executed", {"ok": False}))
    assert fp == ("tool_failure", "tool_executed:?:")


# ---------- defensive: proposals_dir with malformed file ----------


def test_dedupe_skips_unreadable_proposal_files(tmp_path: Path) -> None:
    # Create a prop_*.md without front-matter to make sure the parser
    # is robust.
    (tmp_path / "prop_garbage.md").write_text("no front matter here\n", encoding="utf-8")
    proposals = generate(read_trace(FIXTURE), now=_fixed_now())
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
