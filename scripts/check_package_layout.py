#!/usr/bin/env python3
"""Verify hatch wheel layout and that ``uv build`` succeeds."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _package_roots(wheel: dict) -> list[Path]:
    roots: list[Path] = []
    for pkg in wheel.get("packages", []):
        rel = str(pkg).strip()
        if rel:
            roots.append(ROOT / rel)
    return roots


def _force_include_sources(wheel: dict) -> list[tuple[str, Path]]:
    force_include = wheel.get("force-include", {})
    if not force_include:
        return []
    if not isinstance(force_include, dict):
        return []
    entries: list[tuple[str, Path]] = []
    for src in force_include:
        rel = str(src).strip()
        if rel:
            entries.append((rel, ROOT / rel))
    return entries


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

    package_roots = _package_roots(wheel)
    for pkg_root in package_roots:
        if not pkg_root.is_dir():
            errors.append(f"wheel.packages path missing: {pkg_root.relative_to(ROOT)}")

    for rel, path in _force_include_sources(wheel):
        if not path.exists():
            errors.append(f"force-include source missing: {rel}")
            continue
        for pkg_root in package_roots:
            try:
                path.relative_to(pkg_root)
            except ValueError:
                continue
            errors.append(
                "force-include duplicates wheel.packages content: "
                f"{rel} is already under {pkg_root.relative_to(ROOT)}"
            )
            break

    return errors


def collect_build_errors() -> list[str]:
    result = subprocess.run(
        ["uv", "build"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return []
    detail = (result.stderr or result.stdout or "unknown build error").strip()
    if len(detail) > 1200:
        detail = detail[-1200:]
    return [f"uv build failed:\n{detail}"]


def main() -> int:
    errors = collect_layout_errors()
    if not errors:
        errors = collect_build_errors()
    if errors:
        print("package layout check failed:", file=sys.stderr)
        for msg in errors:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    print("package layout check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
