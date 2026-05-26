#!/usr/bin/env python3
"""Manage the HarnessLab Web UI (``harnesslab serve``).

Usage::

    ./hl-serve start|stop|restart|status|build
    ./hl-serve restart --build
    ./scripts/hl_serve.py build

Environment (all optional):

- ``HL_SERVE_HOST`` — bind address (default: ``127.0.0.1``)
- ``HL_SERVE_PORT`` — TCP port (default: ``8787``)
- ``HL_SERVE_MODEL`` — ``simple`` | ``deepseek`` (default: ``deepseek``)
- ``HL_SERVE_WORKSPACE`` — workspace root (default: repo root)
- ``HL_SERVE_MAX_STEPS`` — inner-loop step budget (default: ``20``)
- ``HL_SERVE_ENV_FILE`` — dotenv-style file (default: ``~/.config/harnesslab/env``)
- ``HARNESSLAB_WEB_UI_VERSION`` — ``legacy`` | ``ts`` (default: ``ts`` when unset;
  server falls back to legacy if ``static_ts/`` is missing)

Model credentials stay out of repo. Set ``DEEPSEEK_API_KEY`` in the shell or
env file (see ``scripts/hl-serve.example.env``).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBUI_DIR = ROOT / "webui"
STATIC_TS_DIR = ROOT / "src" / "harnesslab" / "web" / "static_ts"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harnesslab.core.operator_config import apply_provider_env, load_operator_config  # noqa: E402

STATE_DIR = ROOT / ".harnesslab"
PID_FILE = STATE_DIR / "serve.pid"
LOG_FILE = STATE_DIR / "serve.log"
DEFAULT_ENV_FILE = Path.home() / ".config" / "harnesslab" / "env"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple ``export KEY=value`` / ``KEY=value`` env file."""

    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def apply_env_file(path: Path) -> None:
    for key, value in load_env_file(path).items():
        os.environ.setdefault(key, value)


def port_listener_pids(port: int) -> list[int]:
    try:
        proc = subprocess.run(
            ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    pids: list[int] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def read_pid_file() -> int | None:
    if not PID_FILE.is_file():
        return None
    text = PID_FILE.read_text(encoding="utf-8").strip()
    return int(text) if text.isdigit() else None


def write_pid_file(pid: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid), encoding="utf-8")


def remove_pid_file() -> None:
    PID_FILE.unlink(missing_ok=True)


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def health_ok(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError):
        return False


def fetch_health(host: str, port: int) -> dict | None:
    url = f"http://{host}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def tail_log(lines: int = 5) -> None:
    if not LOG_FILE.is_file():
        return
    content = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in content[-lines:]:
        print(line, file=sys.stderr)


def kill_pids(pids: list[int], *, force: bool = False) -> None:
    sig = signal.SIGKILL if force else signal.SIGTERM
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def resolve_bun_executable() -> Path | None:
    """Return ``bun`` from PATH or ``~/.bun/bin/bun`` when installed there."""

    bun = shutil.which("bun")
    if bun:
        return Path(bun)
    home_bun = Path.home() / ".bun" / "bin" / "bun"
    if home_bun.is_file() and os.access(home_bun, os.X_OK):
        return home_bun
    return None


def build_web_ui() -> int:
    """Run ``bun run build`` in ``webui/`` (Vite → ``static_ts/``)."""

    if not WEBUI_DIR.is_dir():
        print(f"webui directory not found: {WEBUI_DIR}", file=sys.stderr)
        return 1

    bun = resolve_bun_executable()
    if bun is None:
        print(
            "bun not found — install from https://bun.sh or add ~/.bun/bin to PATH",
            file=sys.stderr,
        )
        return 1

    print(f"Building TS web UI ({bun} run build in webui/)...")
    proc = subprocess.run(
        [str(bun), "run", "build"],
        cwd=WEBUI_DIR,
        check=False,
    )
    if proc.returncode != 0:
        print("Web UI build failed", file=sys.stderr)
        return proc.returncode

    print(f"Web UI build ok — output: {STATIC_TS_DIR.relative_to(ROOT)}/")
    return 0


def stop_server(port: int) -> int:
    pids = port_listener_pids(port)
    pid_file_pid = read_pid_file()

    if not pids and pid_file_pid is None:
        print(f"HarnessLab serve is not running on port {port}")
        remove_pid_file()
        return 0

    if pids:
        kill_pids(pids)
        time.sleep(0.3)
        remaining = port_listener_pids(port)
        if remaining:
            kill_pids(remaining, force=True)

    if pid_file_pid is not None and process_alive(pid_file_pid):
        os.kill(pid_file_pid, signal.SIGTERM)

    remove_pid_file()
    print(f"HarnessLab serve stopped (port {port})")
    return 0


def start_server(
    *,
    host: str,
    port: int,
    model: str,
    workspace: Path,
    max_steps: int,
) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if port_listener_pids(port):
        print(f"HarnessLab serve already listening on {host}:{port}")
        if health_ok(host, port):
            print(f"Health: ok — http://{host}:{port}/")
        return 0

    if not workspace.is_dir():
        print(f"workspace not found: {workspace}", file=sys.stderr)
        return 1

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "harnesslab",
            "serve",
            "--host",
            host,
            "--port",
            str(port),
            "--model",
            model,
            "--workspace-root",
            str(workspace),
            "--max-steps",
            str(max_steps),
        ],
        cwd=ROOT,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
        start_new_session=True,
    )
    log_handle.close()
    write_pid_file(proc.pid)

    for _ in range(30):
        if proc.poll() is not None:
            print("Server exited during startup. Last log lines:", file=sys.stderr)
            tail_log()
            remove_pid_file()
            return 1
        if health_ok(host, port):
            print(f"HarnessLab serve started (model={model})")
            print(f"  URL:  http://{host}:{port}/")
            print(f"  Log:  {LOG_FILE}")
            print(f"  PID:  {proc.pid}")
            return 0
        time.sleep(0.2)

    print("Server process started but health check failed. Tail log:", file=sys.stderr)
    print(f"  tail -f {LOG_FILE}", file=sys.stderr)
    return 1


def status_server(host: str, port: int) -> int:
    pids = port_listener_pids(port)
    if not pids:
        print(f"status: stopped (port {port} free)")
        return 1

    print(f"status: running on http://{host}:{port}/")
    print(f"  PIDs: {', '.join(str(p) for p in pids)}")
    pid_file_pid = read_pid_file()
    if pid_file_pid is not None:
        print(f"  pid file: {pid_file_pid}")

    payload = fetch_health(host, port)
    if payload is None:
        print("  health: unreachable (process may still be starting)")
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the HarnessLab Web UI (harnesslab serve).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "commands:\n"
            "  start     bind localhost and launch harnesslab serve\n"
            "  stop      stop the process listening on HL_SERVE_PORT\n"
            "  restart   stop then start (--build to rebuild TS UI first)\n"
            "  build     run bun run build in webui/ (Vite → static_ts/)\n"
            "  status    show PID, port, and /api/health JSON\n"
            "\n"
            "environment (all optional):\n"
            "  HL_SERVE_HOST          bind address (default: 127.0.0.1)\n"
            "  HL_SERVE_PORT          TCP port (default: 8787)\n"
            "  HL_SERVE_MODEL         simple | deepseek | anthropic | openai (default: deepseek)\n"
            "  HL_SERVE_WORKSPACE     workspace root (default: repo root)\n"
            "  HL_SERVE_MAX_STEPS     inner-loop step budget (default: 20)\n"
            "  HL_SERVE_ENV_FILE      dotenv file (default: ~/.config/harnesslab/env)\n"
            "  HARNESSLAB_WEB_UI_VERSION  legacy | ts (default: ts; legacy fallback if no bundle)\n"
            "\n"
            "Model credentials are not stored in-repo. Set DEEPSEEK_API_KEY in the\n"
            "shell or env file (see scripts/hl-serve.example.env).\n"
            "\n"
            "examples:\n"
            "  ./hl-serve start\n"
            "  ./hl-serve build\n"
            "  ./hl-serve restart --build\n"
            "  HL_SERVE_PORT=8788 ./hl-serve restart\n"
            "  ./hl-serve status"
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "stop", "restart", "build", "status"],
        help="action to perform (omit to print this help)",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="with restart: rebuild TS web UI (webui/) before starting serve",
    )
    return parser


def resolve_settings() -> tuple[str, int, str, Path, int]:
    env_file = Path(os.environ.get("HL_SERVE_ENV_FILE", str(DEFAULT_ENV_FILE)))
    apply_env_file(env_file)
    try:
        config = load_operator_config()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    apply_provider_env(config)
    host = os.environ.get("HL_SERVE_HOST", config.serve_host)
    port = int(os.environ.get("HL_SERVE_PORT", str(config.serve_port)))
    model = os.environ.get("HL_SERVE_MODEL", config.model_backend)
    workspace = Path(os.environ.get("HL_SERVE_WORKSPACE", str(ROOT))).resolve()
    max_steps = int(os.environ.get("HL_SERVE_MAX_STEPS", str(config.serve_max_steps)))
    return host, port, model, workspace, max_steps


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    host, port, model, workspace, max_steps = resolve_settings()

    if args.command == "start":
        return start_server(
            host=host,
            port=port,
            model=model,
            workspace=workspace,
            max_steps=max_steps,
        )
    if args.command == "stop":
        return stop_server(port)
    if args.command == "build":
        if args.build:
            print("--build applies only to restart", file=sys.stderr)
            return 2
        return build_web_ui()
    if args.command == "restart":
        if args.build:
            code = build_web_ui()
            if code != 0:
                return code
        stop_server(port)
        return start_server(
            host=host,
            port=port,
            model=model,
            workspace=workspace,
            max_steps=max_steps,
        )
    if args.build:
        print("--build applies only to restart", file=sys.stderr)
        return 2
    return status_server(host, port)


if __name__ == "__main__":
    raise SystemExit(main())
