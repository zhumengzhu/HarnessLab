"""Load operator secrets from ``~/.config/harnesslab/env``."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = Path.home() / ".config" / "harnesslab" / "env"


def env_file_path() -> Path:
    raw = (os.environ.get("HL_SERVE_ENV_FILE") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_ENV_FILE


def parse_env_file(path: Path) -> dict[str, str]:
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


def apply_env_file(path: Path | None = None, *, overwrite: bool = False) -> Path | None:
    """Apply key/value pairs from the operator env file into ``os.environ``."""

    target = path or env_file_path()
    if not target.is_file():
        return None
    for key, value in parse_env_file(target).items():
        if overwrite:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)
    return target
