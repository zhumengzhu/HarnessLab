"""Tests for scripts/check_package_layout.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_checker() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_package_layout.py"
    spec = importlib.util.spec_from_file_location("check_package_layout", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_layout_errors_empty_when_force_include_exists() -> None:
    checker = _load_checker()
    errors = checker.collect_layout_errors()
    assert errors == []


def test_collect_layout_errors_reports_missing_force_include(
    tmp_path: Path, monkeypatch
) -> None:
    checker = _load_checker()
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.hatch.build.targets.wheel]
packages = ["src/harnesslab"]

[tool.hatch.build.targets.wheel.force-include]
"missing/path" = "harnesslab/missing"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "PYPROJECT", pyproject)
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    errors = checker.collect_layout_errors()
    assert any("missing/path" in msg for msg in errors)
