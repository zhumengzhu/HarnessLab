"""Process-scoped OTel Resource snapshot for span export."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

from harnesslab.telemetry.span_attributes import (
    DEPLOYMENT_ENVIRONMENT,
    HARNESSLAB_WORKSPACE,
    SERVICE_INSTANCE_ID,
    SERVICE_NAME,
    SERVICE_VERSION,
)


def package_version() -> str:
    try:
        from importlib.metadata import version

        return version("harnesslab")
    except Exception:
        return "0.0.0"


def build_process_resource(
    workspace_root: Path | None = None,
    *,
    deployment_environment: str | None = None,
) -> dict[str, Any]:
    env = (
        deployment_environment
        or os.environ.get("HARNESSLAB_DEPLOYMENT_ENV", "").strip()
        or "local"
    )
    host = socket.gethostname()
    pid = os.getpid()
    resource: dict[str, Any] = {
        SERVICE_NAME: "harnesslab",
        SERVICE_VERSION: package_version(),
        SERVICE_INSTANCE_ID: f"{host}:{pid}",
        DEPLOYMENT_ENVIRONMENT: env,
    }
    if workspace_root is not None:
        resource[HARNESSLAB_WORKSPACE] = workspace_root.name
    return resource
