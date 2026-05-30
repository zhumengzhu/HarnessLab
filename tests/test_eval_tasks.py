"""Integration test: every shipped YAML task must pass against the current loop.

This is the contract that keeps `eval/baseline.json` honest. If a real
regression is introduced, this test will fail loud before pre-commit
even has a chance to look at the baseline diff.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harnesslab.eval.loader import load_suite
from harnesslab.eval.runner import TaskRunner
from harnesslab.eval.task import TaskSuite

TASKS_DIR = Path(__file__).resolve().parents[1] / "eval" / "tasks"


def test_shipped_tasks_all_pass() -> None:
    suite = load_suite(TASKS_DIR)
    offline = TaskSuite(
        tasks=[t for t in suite.tasks if "network" not in t.tags]
    )
    assert offline.tasks, "no offline eval tasks found"

    results = TaskRunner().run(offline)
    failures = [(r.task_name, r.failures) for r in results if not r.passed]
    assert not failures, f"failing tasks: {failures}"


@pytest.mark.network
def test_network_tasks_pass_when_live() -> None:
    import os

    if os.getenv("RUN_LIVE_EVAL") != "1":
        pytest.skip("set RUN_LIVE_EVAL=1 to run network-dependent eval tasks")

    suite = load_suite(TASKS_DIR)
    network = TaskSuite(tasks=[t for t in suite.tasks if "network" in t.tags])
    assert network.tasks, "expected at least one network-tagged task"

    results = TaskRunner().run(network)
    failures = [(r.task_name, r.failures) for r in results if not r.passed]
    assert not failures, f"failing network tasks: {failures}"


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
        "grep_then_edit",
        "compaction_on_threshold",
        "session_resume_second_turn",
        "session_memory_persists",
        "apply_patch_unified_diff",
        "fetch_url_weather",
        "shell_profile_strict",
        "workspace_memory_persists",
        "plan_then_execute",
        "research_summary",
        "spawn_sub_agent_roundtrip",
        "supervisor_research_then_write",
        "budget_cost_hard_stop",
        "budget_cost_soft_threshold",
    } <= names
