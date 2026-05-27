"""Read-only HTTP fetch with profile-aware policy controls (Phase 5.1)."""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterable
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import ToolCall, ToolResult
from harnesslab.tools.research_tools import (
    is_textlike_content_type,
    robots_advisory_for_url,
)

# Hosts permitted for ``fetch_url`` in *strict* mode only. In ``open`` mode
# (now the default) the allowlist is ignored and every public HTTPS host is
# reachable, subject to SSRF protection below. ``wttr.in`` is the historical
# example used by the deterministic eval suite.
DEFAULT_FETCH_HOST_ALLOWLIST: frozenset[str] = frozenset(
    {
        "wttr.in",
    }
)

# Hosts that are *always* denied regardless of mode — cloud-metadata
# endpoints, the IPv4 link-local block reachable through DNS, and obvious
# loopback aliases. Operators can extend this via ``fetch_url.deny_hosts``.
DEFAULT_FETCH_DENY_HOSTS: frozenset[str] = frozenset(
    {
        "metadata.google.internal",
        "metadata",
        "169.254.169.254",
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
    }
)

DEFAULT_FETCH_TIMEOUT_SECONDS = 10.0
DEFAULT_JINA_READER_BASE = "https://r.jina.ai"
DEFAULT_FETCH_PROVIDER: Literal["direct", "jina"] = "direct"
# Open by default — MVP harness is operator-controlled and a strict
# allowlist proved too restrictive for everyday research tasks (see
# product feedback comparing to OpenClaw-style agents). Operators can
# pin ``fetch_url.mode = "strict"`` in the config to restore an
# allowlist-only posture.
DEFAULT_FETCH_MODE: Literal["strict", "open"] = "open"


def parse_csv_hosts(value: str | Iterable[str] | None) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = [str(v) for v in value]
    out = set()
    for item in raw_items:
        host = item.strip().lower()
        if host:
            out.add(host)
    return frozenset(out)


def _is_private_or_local_address(host: str) -> bool:
    """Return True when ``host`` resolves to a private/loopback/link-local IP."""

    candidates: list[str] = []
    # Treat literal IP hostnames directly without DNS lookups.
    try:
        ipaddress.ip_address(host)
        candidates.append(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError:
            # If DNS fails we err on the side of allowing the call and
            # letting httpx surface the real failure to the caller —
            # otherwise a transient DNS hiccup would look like a policy
            # block, which is much harder to debug.
            return False
        for info in infos:
            addr = info[4][0]
            candidates.append(addr.split("%", 1)[0])
    for raw in candidates:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    return False


def validate_fetch_url(
    url: str,
    *,
    allowlist: frozenset[str] | None = None,
    deny_hosts: frozenset[str] | None = None,
    mode: Literal["strict", "open"] = DEFAULT_FETCH_MODE,
) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for a candidate URL."""

    text = (url or "").strip()
    if not text:
        return False, "missing url"
    parsed = urlparse(text)
    if parsed.scheme not in {"https", "http"}:
        return False, "url scheme must be http or https"
    if mode == "open" and parsed.scheme != "https":
        return False, "url scheme must be https in open mode"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "missing url host"
    explicit_deny = deny_hosts if deny_hosts is not None else frozenset()
    combined_deny = explicit_deny | DEFAULT_FETCH_DENY_HOSTS
    if host in combined_deny:
        return False, f"host '{host}' is on fetch denylist"
    if mode == "strict":
        allowed = allowlist if allowlist is not None else DEFAULT_FETCH_HOST_ALLOWLIST
        if host not in allowed:
            return False, f"host '{host}' not on fetch allowlist ({', '.join(sorted(allowed))})"
    if mode == "open" and _is_private_or_local_address(host):
        return False, (
            f"host '{host}' resolves to a private/loopback/link-local "
            "address; refusing to fetch (SSRF protection)"
        )
    if parsed.username or parsed.password:
        return False, "embedded credentials in url are not allowed"
    return True, "ok"


def jina_reader_url(url: str) -> str:
    """Wrap a public HTTPS URL for Jina Reader."""

    return f"{DEFAULT_JINA_READER_BASE}/{url}"


def resolve_jina_api_key(configured_env: str | None) -> str | None:
    if configured_env:
        value = (os.environ.get(configured_env) or "").strip()
        if value:
            return value
    return (os.environ.get("JINA_API_KEY") or "").strip() or None


class FetchUrlTool:
    """GET an HTTPS URL and return the response body as text."""

    name = "fetch_url"
    description = (
        "Fetch read-only text from an HTTPS URL on the public internet. "
        "Use for live external facts (docs, blogs, weather via "
        "https://wttr.in/City?format=3 , GitHub raw content, etc.). "
        "Private/loopback/link-local addresses and cloud-metadata hosts "
        "are blocked. Operators may pin a stricter allowlist; in that "
        "mode only hosts on the operator allowlist are reachable. "
        "When provider=jina, the URL is fetched via Jina Reader "
        "(markdown, JS-friendly) while policy still applies to the "
        "original URL."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": (
                    "Full HTTPS URL on the public internet (HTTP also "
                    "allowed in strict mode only)."
                ),
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        limits: RuntimeLimits | None = None,
        host_allowlist: frozenset[str] | None = None,
        deny_hosts: frozenset[str] | None = None,
        mode: Literal["strict", "open"] = DEFAULT_FETCH_MODE,
        check_robots_advisory: bool = True,
        provider: Literal["direct", "jina"] = DEFAULT_FETCH_PROVIDER,
        jina_api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    ) -> None:
        self._limits = limits or RuntimeLimits()
        self._host_allowlist = host_allowlist or DEFAULT_FETCH_HOST_ALLOWLIST
        self._deny_hosts = deny_hosts or frozenset()
        self._mode = mode
        self._check_robots_advisory = check_robots_advisory
        self._provider = provider
        self._jina_api_key = (jina_api_key or "").strip() or None
        self._timeout = timeout_seconds
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def execute(self, call: ToolCall) -> ToolResult:
        url = str(call.args.get("url", "")).strip()
        ok, reason = validate_fetch_url(
            url,
            allowlist=self._host_allowlist,
            deny_hosts=self._deny_hosts,
            mode=self._mode,
        )
        if not ok:
            return ToolResult(ok=False, output="", error=reason)
        fetch_url = jina_reader_url(url) if self._provider == "jina" else url
        headers: dict[str, str] = {}
        if self._provider == "jina" and self._jina_api_key:
            headers["Authorization"] = f"Bearer {self._jina_api_key}"
        try:
            response = self._client.get(fetch_url, headers=headers or None)
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            if self._provider != "jina" and not is_textlike_content_type(content_type):
                return ToolResult(
                    ok=False,
                    output="",
                    error=(
                        "unsupported content-type for fetch_url: "
                        f"{content_type or 'unknown'}; use read_pdf, provider=jina, "
                        "or another tool"
                    ),
                )
            body = response.text
            if self._provider == "jina":
                body = f"(via Jina Reader)\n\n{body}"
            if self._check_robots_advisory and self._mode == "open" and self._provider == "direct":
                advisory = robots_advisory_for_url(self._client, url)
                if advisory:
                    body = f"{advisory}\n\n{body}"
            cap = self._limits.output_bytes_cap
            if len(body.encode("utf-8")) > cap:
                body = body.encode("utf-8")[:cap].decode("utf-8", errors="replace")
                body += "\n(truncated)"
            return ToolResult(ok=True, output=body)
        except httpx.HTTPStatusError as exc:
            return ToolResult(
                ok=False,
                output="",
                error=f"HTTP {exc.response.status_code} from {url}",
            )
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))
