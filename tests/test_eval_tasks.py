"""Integration test: every shipped YAML task must pass against the current loop.

This is the contract that keeps `eval/baseline.json` honest. If a real
regression is introduced, this test will fail loud before pre-commit
even has a chance to look at the baseline diff.
"""

from __future__ import annotations

from pathlib import Path

from harnesslab.eval.loader import load_suite
from harnesslab.eval.runner import TaskRunner

TASKS_DIR = Path(__file__).resolve().parents[1] / "eval" / "tasks"


def test_shipped_tasks_all_pass() -> None:
    suite = load_suite(TASKS_DIR)
    assert suite.tasks, "no eval tasks found"

    results = TaskRunner().run(suite)
    failures = [(r.task_name, r.failures) for r in results if not r.passed]
    assert not failures, f"failing tasks: {failures}"


def test_shipped_tasks_cover_expected_paths() -> None:
    """Sanity: ensure we ship coverage across all key code paths."""
    suite = load_suite(TASKS_DIR)
    names = {t.name for t in suite.tasks}
    assert {
        "assistant_fallback",
        "write_then_read",
        "policy_denied_path",
        "invalid_args_schema",
        "shell_denylist_blocks",
        "multi_step_tool_then_final",
    } <= names
