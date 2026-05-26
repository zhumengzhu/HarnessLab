"""Unit tests for scripts/hl_serve.py helpers."""

from __future__ import annotations

import importlib.util
import subprocess
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
    assert "build" in out
    assert "--build" in out


def test_resolve_bun_prefers_path(monkeypatch) -> None:
    monkeypatch.setattr(_HL_SERVE.shutil, "which", lambda _name: "/usr/local/bin/bun")
    assert _HL_SERVE.resolve_bun_executable() == Path("/usr/local/bin/bun")


def test_resolve_bun_falls_back_to_home_bun(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(_HL_SERVE.shutil, "which", lambda _name: None)
    home = tmp_path / "home"
    home.mkdir()
    home_bun = home / ".bun" / "bin" / "bun"
    home_bun.parent.mkdir(parents=True)
    home_bun.write_text("", encoding="utf-8")
    home_bun.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    assert _HL_SERVE.resolve_bun_executable() == home_bun


def test_build_web_ui_runs_bun_build(monkeypatch, tmp_path: Path) -> None:
    webui = tmp_path / "webui"
    webui.mkdir()
    (webui / "package.json").write_text("{}", encoding="utf-8")
    bun = tmp_path / "bun"
    bun.write_text("", encoding="utf-8")
    bun.chmod(0o755)
    monkeypatch.setattr(_HL_SERVE, "WEBUI_DIR", webui)
    monkeypatch.setattr(_HL_SERVE, "STATIC_TS_DIR", tmp_path / "static_ts")
    monkeypatch.setattr(_HL_SERVE, "ROOT", tmp_path)
    monkeypatch.setattr(_HL_SERVE, "resolve_bun_executable", lambda: bun)

    calls: list[list[str]] = []

    def fake_run(cmd, *, cwd, check):  # noqa: ANN001
        calls.append(cmd)
        assert cwd == webui
        assert check is False
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(_HL_SERVE.subprocess, "run", fake_run)
    assert _HL_SERVE.build_web_ui() == 0
    assert calls == [[str(bun), "run", "build"]]


def test_build_flag_without_restart_errors(capsys) -> None:
    assert _HL_SERVE.main(["build", "--build"]) == 2
    err = capsys.readouterr().err
    assert "--build applies only to restart" in err
