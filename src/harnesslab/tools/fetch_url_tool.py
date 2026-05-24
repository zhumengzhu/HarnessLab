"""Read-only HTTP fetch with a host allowlist (MVP external data)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import ToolCall, ToolResult

# Hosts permitted for ``fetch_url``. Expand deliberately — not a general
# web browser. ``wttr.in`` covers ASCII weather without API keys.
DEFAULT_FETCH_HOST_ALLOWLIST: frozenset[str] = frozenset(
    {
        "wttr.in",
    }
)

DEFAULT_FETCH_TIMEOUT_SECONDS = 10.0


def validate_fetch_url(url: str, *, allowlist: frozenset[str] | None = None) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for a candidate URL."""

    text = (url or "").strip()
    if not text:
        return False, "missing url"
    parsed = urlparse(text)
    if parsed.scheme not in {"https", "http"}:
        return False, "url scheme must be http or https"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "missing url host"
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
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    ) -> None:
        self._limits = limits or RuntimeLimits()
        self._host_allowlist = host_allowlist or DEFAULT_FETCH_HOST_ALLOWLIST
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
        ok, reason = validate_fetch_url(url, allowlist=self._host_allowlist)
        if not ok:
            return ToolResult(ok=False, output="", error=reason)
        try:
            response = self._client.get(url)
            response.raise_for_status()
            body = response.text
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
