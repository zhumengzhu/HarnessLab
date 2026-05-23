"""Unit tests for the eval framework: loader, runner, baseline, report."""

from __future__ import annotations

from pathlib import Path

import pytest

from harnesslab.core.models import TraceEvent
from harnesslab.eval.baseline import (
    Baseline,
    BaselineEntry,
    compare,
    load_baseline,
    save_baseline,
)
from harnesslab.eval.loader import load_suite, load_task
from harnesslab.eval.report import render_stdout, write_json
from harnesslab.eval.runner import TaskRunner, _payload_contains
from harnesslab.eval.task import (
    ExpectedEvent,
    Task,
    TaskExpected,
    TaskMetrics,
    TaskResult,
    TaskTurn,
)

# ---------- loader ----------


def _write_yaml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_load_task_parses_yaml(tmp_path: Path) -> None:
    f = tmp_path / "t.yaml"
    _write_yaml(
        f,
        """
        name: t
        goal: probe
        turns:
          - input: hello
        expected:
          final_reply_contains: ["HarnessLab"]
        """,
    )
    task = load_task(f)
    assert task.name == "t"
    assert task.turns[0].input == "hello"
    assert task.expected.final_reply_contains == ["HarnessLab"]


def test_load_suite_returns_tasks_in_lexicographic_order(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "02_b.yaml",
        "name: b\ngoal: x\nturns:\n  - input: hi\n",
    )
    _write_yaml(
        tmp_path / "01_a.yaml",
        "name: a\ngoal: x\nturns:\n  - input: hi\n",
    )
    suite = load_suite(tmp_path)
    assert [t.name for t in suite.tasks] == ["a", "b"]


# ---------- payload subset ----------


@pytest.mark.parametrize(
    ("actual", "expected", "want"),
    [
        ({"a": 1, "b": 2}, {"a": 1}, True),
        ({"a": 1}, {"a": 2}, False),
        ({"a": {"b": 1, "c": 2}}, {"a": {"b": 1}}, True),
        ({"a": {"b": 1}}, {"a": {"b": 1, "c": 2}}, False),
        ({}, {"a": 1}, False),
        ({"a": 1}, {}, True),
    ],
)
def test_payload_contains(actual: dict, expected: dict, want: bool) -> None:
    assert _payload_contains(actual, expected) is want


# ---------- runner ----------


def _result_of(task: Task) -> TaskResult:
    return TaskRunner().run_one(task)


def test_runner_passes_assistant_fallback() -> None:
    task = Task(
        name="probe",
        goal="g",
        turns=[TaskTurn(input="hello")],
        expected=TaskExpected(
            final_reply_contains=["HarnessLab is ready"],
            no_event_types=["tool_executed", "tool_denied", "tool_invalid_args"],
        ),
    )
    result = _result_of(task)
    assert result.passed, result.failures
    assert result.metrics.tool_calls == 0


def test_runner_fails_when_expected_event_missing() -> None:
    task = Task(
        name="missing-evt",
        goal="g",
        turns=[TaskTurn(input="hello")],
        expected=TaskExpected(events_include=[ExpectedEvent(event_type="tool_executed")]),
    )
    result = _result_of(task)
    assert result.passed is False
    assert any("tool_executed" in f for f in result.failures)


def test_runner_fails_when_forbidden_event_appears() -> None:
    task = Task(
        name="forbidden",
        goal="g",
        turns=[TaskTurn(input='/tool read_file {"path":"../escape"}')],
        expected=TaskExpected(no_event_types=["tool_denied"]),
    )
    result = _result_of(task)
    assert result.passed is False
    assert any("tool_denied" in f for f in result.failures)


def test_runner_counts_metrics_correctly() -> None:
    task = Task(
        name="metrics",
        goal="g",
        turns=[
            TaskTurn(input='/tool write_file {"path":"a.txt","content":"x"}'),
            TaskTurn(input='/tool read_file {"path":"a.txt"}'),
        ],
    )
    result = _result_of(task)
    assert result.metrics.turns == 2
    assert result.metrics.tool_calls == 2
    assert result.metrics.tool_failures == 0
    assert result.metrics.denials == 0
    assert result.metrics.invalid_args == 0


def test_runner_payload_contains_match() -> None:
    task = Task(
        name="payload",
        goal="g",
        turns=[TaskTurn(input='/tool write_file {"path":"a.txt","content":"x"}')],
        expected=TaskExpected(
            events_include=[
                ExpectedEvent(
                    event_type="tool_executed",
                    payload_contains={"tool": "write_file", "ok": True},
                )
            ],
        ),
    )
    result = _result_of(task)
    assert result.passed, result.failures


# ---------- baseline + compare ----------


def _result(name: str, passed: bool = True, **m: int) -> TaskResult:
    return TaskResult(
        task_name=name,
        passed=passed,
        failures=[] if passed else ["sample failure"],
        metrics=TaskMetrics(
            turns=m.get("turns", 1),
            tool_calls=m.get("tool_calls", 0),
            tool_failures=m.get("tool_failures", 0),
            denials=m.get("denials", 0),
            invalid_args=m.get("invalid_args", 0),
        ),
        final_reply="",
    )


def test_baseline_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    save_baseline(path, [_result("a", passed=True, tool_calls=2)])
    loaded = load_baseline(path)
    assert loaded is not None
    assert loaded.results["a"].passed is True
    assert loaded.results["a"].metrics.tool_calls == 2


def test_load_baseline_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_baseline(tmp_path / "missing.json") is None


def test_compare_returns_empty_without_baseline() -> None:
    assert compare([_result("a")], None) == []


def test_compare_flags_pass_to_fail() -> None:
    baseline = Baseline(
        results={"a": BaselineEntry(passed=True, metrics=_result("a").metrics)}
    )
    regressions = compare([_result("a", passed=False)], baseline)
    assert len(regressions) == 1
    assert regressions[0].kind == "task_now_failing"


def test_compare_flags_tool_failures_increase() -> None:
    baseline = Baseline(
        results={
            "a": BaselineEntry(passed=True, metrics=_result("a").metrics),
        }
    )
    regressions = compare([_result("a", tool_failures=1)], baseline)
    assert any(r.kind == "tool_failures_increased" for r in regressions)


def test_compare_flags_invalid_args_increase() -> None:
    baseline = Baseline(
        results={"a": BaselineEntry(passed=True, metrics=_result("a").metrics)}
    )
    regressions = compare([_result("a", invalid_args=1)], baseline)
    assert any(r.kind == "invalid_args_increased" for r in regressions)


def test_compare_ignores_tool_calls_increase() -> None:
    baseline = Baseline(
        results={"a": BaselineEntry(passed=True, metrics=_result("a").metrics)}
    )
    # tool_calls going up is informational, not a regression.
    regressions = compare([_result("a", tool_calls=99)], baseline)
    assert regressions == []


# ---------- report ----------


def test_render_stdout_includes_pass_fail_and_summary() -> None:
    out = render_stdout(
        [_result("a", passed=True), _result("b", passed=False)],
        regressions=[],
    )
    assert "[PASS] a" in out
    assert "[FAIL] b" in out
    assert "1/2 passed" in out


def test_render_stdout_lists_regressions() -> None:
    from harnesslab.eval.baseline import Regression

    out = render_stdout(
        [_result("a", passed=False)],
        regressions=[Regression(task_name="a", kind="task_now_failing", detail="x")],
    )
    assert "REGRESSIONS:" in out
    assert "task_now_failing" in out


def test_write_json_emits_full_payload(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_json(path, [_result("a")], regressions=[])
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert '"task_name": "a"' in content
    assert '"regressions": []' in content


# ---------- replay-decision path ----------


def test_runner_uses_replay_model_when_decisions_present() -> None:
    from harnesslab.core.models import Decision

    task = Task(
        name="replay",
        goal="replay-driven",
        decisions=[
            Decision(kind="final", assistant_message="canned reply"),
        ],
        turns=[TaskTurn(input="ignored because ReplayModel ignores input")],
        expected=TaskExpected(final_reply_contains=["canned reply"]),
    )
    result = _result_of(task)
    assert result.passed, result.failures
    assert result.final_reply == "canned reply"


def test_runner_drives_multi_step_turn_via_max_steps() -> None:
    """Phase 2.1: a single turn with max_steps>1 must consume multiple
    pre-recorded decisions and terminate on the terminal one."""
    from harnesslab.core.models import Decision

    task = Task(
        name="multi_step",
        goal="multi-step",
        decisions=[
            Decision(
                kind="tool",
                tool_name="write_file",
                tool_args={"path": "a.txt", "content": "x"},
            ),
            Decision(kind="final", assistant_message="all wrapped up"),
        ],
        turns=[TaskTurn(input="go", max_steps=2)],
        expected=TaskExpected(
            final_reply_contains=["all wrapped up"],
            events_include=[
                ExpectedEvent(
                    event_type="tool_executed",
                    payload_contains={"tool": "write_file", "ok": True},
                ),
                ExpectedEvent(
                    event_type="session_finished",
                    payload_contains={"reason": "final", "steps": 2},
                ),
            ],
        ),
    )
    result = _result_of(task)
    assert result.passed, result.failures
    assert result.metrics.tool_calls == 1


def test_runner_honors_task_limits_for_compaction() -> None:
    from harnesslab.core.models import Decision
    from harnesslab.eval.task import TaskLimits

    long_body = "x" * 200
    task = Task(
        name="compact",
        goal="g",
        limits=TaskLimits(compaction_threshold_tokens=40, compaction_keep_last_messages=2),
        decisions=[
            Decision(kind="final", assistant_message=long_body),
            Decision(kind="final", assistant_message="ok"),
        ],
        turns=[
            TaskTurn(input="one"),
            TaskTurn(input="two"),
        ],
        expected=TaskExpected(
            events_include=[ExpectedEvent(event_type="compaction_started")],
        ),
    )
    result = _result_of(task)
    assert result.passed, result.failures


# ---------- determinism ----------


def test_runner_is_deterministic_across_runs() -> None:
    task = Task(
        name="deterministic",
        goal="g",
        turns=[TaskTurn(input='/tool read_file {"path":"../escape"}')],
    )
    r1, r2 = _result_of(task), _result_of(task)
    assert r1.model_dump() == r2.model_dump()


# ---------- helper trace shape used above (sanity) ----------


def test_traceevent_is_serializable() -> None:
    e = TraceEvent(run_id="r", session_id="s", event_type="x")
    assert e.model_dump()["event_type"] == "x"
