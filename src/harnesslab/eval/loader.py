"""YAML loaders for eval tasks and suites."""

from __future__ import annotations

from pathlib import Path

import yaml

from harnesslab.eval.task import Task, TaskSuite


def load_task(path: Path) -> Task:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Task.model_validate(data)


def load_suite(tasks_dir: Path) -> TaskSuite:
    """Load every ``*.yaml`` file in ``tasks_dir`` into a TaskSuite.

    Files are loaded in lexicographic order so that prefixing task files
    with ``NN_`` produces a stable run order.
    """

    paths = sorted(tasks_dir.glob("*.yaml"))
    tasks = [load_task(p) for p in paths]
    return TaskSuite(tasks=tasks)
