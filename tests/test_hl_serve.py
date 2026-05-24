"""Unit tests for scripts/hl_serve.py helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "hl_serve", _ROOT / "scripts" / "hl_serve.py"
)
assert _SPEC and _SPEC.loader
_HL_SERVE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HL_SERVE)
load_env_file = _HL_SERVE.load_env_file


def test_load_env_file_parses_export_and_comments(tmp_path: Path) -> None:
    path = tmp_path / "env"
    path.write_text(
        "\n".join(
            [
                "# comment",
                "export DEEPSEEK_API_KEY='secret'",
                "HL_SERVE_PORT=8788",
                "INVALID",
            ]
        ),
        encoding="utf-8",
    )
    assert load_env_file(path) == {
        "DEEPSEEK_API_KEY": "secret",
        "HL_SERVE_PORT": "8788",
    }


def test_load_env_file_missing_returns_empty(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "missing") == {}


def test_main_without_command_prints_help(capsys) -> None:
    assert _HL_SERVE.main([]) == 0
    out = capsys.readouterr().out
    assert "HL_SERVE_PORT" in out
    assert "start" in out
