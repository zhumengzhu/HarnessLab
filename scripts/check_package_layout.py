#!/usr/bin/env python3
"""Verify hatch wheel package roots and force-include paths exist on disk."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def collect_layout_errors() -> list[str]:
    if not PYPROJECT.is_file():
        return [f"pyproject.toml not found: {PYPROJECT}"]

    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    wheel = (
        data.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
    )
    errors: list[str] = []

    for pkg in wheel.get("packages", []):
        rel = str(pkg).strip()
        if not rel:
            continue
        path = ROOT / rel
        if not path.is_dir():
            errors.append(f"wheel.packages path missing: {rel}")

    force_include = wheel.get("force-include", {})
    if not isinstance(force_include, dict):
        errors.append("wheel.force-include must be a table")
        return errors

    for src in force_include:
        rel = str(src).strip()
        if not rel:
            continue
        path = ROOT / rel
        if not path.exists():
            errors.append(f"force-include source missing: {rel}")

    return errors


def main() -> int:
    errors = collect_layout_errors()
    if errors:
        print("package layout check failed:", file=sys.stderr)
        for msg in errors:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    print("package layout check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
