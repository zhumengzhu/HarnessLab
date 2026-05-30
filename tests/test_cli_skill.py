"""Tests for ``harnesslab skill`` CLI and catalog index loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesslab import cli
from harnesslab.skills.catalog import (
    install_skill_from_catalog,
    list_skill_records,
    remove_skill,
)
from harnesslab.skills.index_loader import load_catalog_entries


def test_cli_skill_list_includes_bundled_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["harnesslab", "skill", "--workspace-root", str(tmp_path), "list"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "compact\tcatalog" in out
    assert "humanizer\tcatalog" in out


def test_cli_skill_install_from_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "skill",
            "--workspace-root",
            str(tmp_path),
            "install",
            "--catalog-id",
            "compact",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    installed = tmp_path / "skills" / "compact.md"
    assert installed.is_file()
    assert "/compact" in installed.read_text(encoding="utf-8")
    assert "installed:" in capsys.readouterr().out


def test_cli_skill_remove_workspace_skill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install_skill_from_catalog(tmp_path, "compact")
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "skill",
            "--workspace-root",
            str(tmp_path),
            "remove",
            "compact",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    assert not (tmp_path / "skills" / "compact.md").exists()
    assert "removed:" in capsys.readouterr().out


def test_cli_skill_search_matches_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "harnesslab",
            "skill",
            "--workspace-root",
            str(tmp_path),
            "search",
            "humanizer",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == cli.EXIT_OK
    assert "humanizer\tcatalog" in capsys.readouterr().out


def test_local_catalog_index_install(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "demo.md").write_text("# Demo\n\nSample skill.\n", encoding="utf-8")
    index_path = bundle / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "version": 1,
                "skills": [
                    {
                        "id": "demo",
                        "name": "demo",
                        "description": "Sample skill",
                        "tags": ["demo"],
                        "source": "demo.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    entries = load_catalog_entries(str(index_path))
    assert entries[0].name == "demo"
    dest = install_skill_from_catalog(
        tmp_path,
        "demo",
        catalog_sources=(str(index_path),),
    )
    assert dest.is_file()
    records = list_skill_records(tmp_path, catalog_sources=(str(index_path),))
    assert any(record.name == "demo" and record.scope == "workspace" for record in records)
    remove_skill(tmp_path, "demo")
    assert not dest.exists()
