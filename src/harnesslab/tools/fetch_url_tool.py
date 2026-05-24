"""Read-only HTTP fetch with profile-aware policy controls (Phase 5.1)."""

from __future__ import annotations

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

# Hosts permitted for ``fetch_url``. Expand deliberately — not a general
# web browser. ``wttr.in`` covers ASCII weather without API keys.
DEFAULT_FETCH_HOST_ALLOWLIST: frozenset[str] = frozenset(
    {
        "wttr.in",
    }
)

DEFAULT_FETCH_TIMEOUT_SECONDS = 10.0
DEFAULT_FETCH_MODE: Literal["strict", "open"] = "strict"


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
    denied = deny_hosts if deny_hosts is not None else frozenset()
    if host in denied:
        return False, f"host '{host}' is on fetch denylist"
    if mode == "strict":
        allowed = allowlist if allowlist is not None else DEFAULT_FETCH_HOST_ALLOWLIST
        if host not in allowed:
            return False, f"host '{host}' not on fetch allowlist ({', '.join(sorted(allowed))})"
    if parsed.username or parsed.password:
        return False, "embedded credentials in url are not allowed"
    return True, "ok"


class FetchUrlTool:
    """GET a allowlisted URL and return the response body as text."""

    name = "fetch_url"
    description = (
        "Fetch read-only text from an allowlisted HTTPS/HTTP URL. "
        "Use for live external facts such as weather via "
        "https://wttr.in/City?format=3 . Only hosts on the policy "
        "allowlist are permitted."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL (host must be allowlisted, e.g. wttr.in).",
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
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    ) -> None:
        self._limits = limits or RuntimeLimits()
        self._host_allowlist = host_allowlist or DEFAULT_FETCH_HOST_ALLOWLIST
        self._deny_hosts = deny_hosts or frozenset()
        self._mode = mode
        self._check_robots_advisory = check_robots_advisory
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
        try:
            response = self._client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            if not is_textlike_content_type(content_type):
                return ToolResult(
                    ok=False,
                    output="",
                    error=(
                        "unsupported content-type for fetch_url: "
                        f"{content_type or 'unknown'}; use read_pdf or another tool"
                    ),
                )
            body = response.text
            if self._check_robots_advisory and self._mode == "open":
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
