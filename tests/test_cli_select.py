"""CLI smoke for harnesslab select."""

from __future__ import annotations

import pytest

from harnesslab import cli


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["harnesslab", "select", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return int(exc.value.code)


def test_select_list_baseline_only(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    code = _run(monkeypatch, ["list", "--workspace-root", str(tmp_path), "--json"])
    assert code == cli.EXIT_OK
