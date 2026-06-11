"""Pytest configuration: expose ``tests/`` helpers for flat imports."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

# Hostnames used in fetch_url / policy tests. Fake-IP VPNs (e.g. Clash
# ``198.18.0.0/15``) resolve these to benchmark addresses that SSRF
# checks reject; pin stable public literals so tests stay deterministic.
_PUBLIC_TEST_DNS: dict[str, str] = {
    "example.com": "93.184.216.34",
    "wttr.in": "93.184.216.34",
    "github.com": "140.82.121.4",
}


@pytest.fixture(autouse=True)
def stable_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    real_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(
        host: str,
        port: object,
        *args: object,
        **kwargs: object,
    ) -> list[tuple]:
        mapped = _PUBLIC_TEST_DNS.get(str(host).lower())
        if mapped:
            return real_getaddrinfo(mapped, port, *args, **kwargs)
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", patched_getaddrinfo)
