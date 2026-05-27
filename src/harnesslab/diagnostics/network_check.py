"""Network diagnostics for web research tools."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import httpx

from harnesslab.core.operator_config import load_operator_config
from harnesslab.tools.research_tools import (
    DEFAULT_WEB_SEARCH_BACKEND,
    WebSearchTool,
    _duckduckgo_antibot_page,
    _search_ddgs,
    _search_duckduckgo,
    resolve_web_search_api_key,
)

CheckStatus = Literal["ok", "warn", "fail", "skip"]


@dataclass(frozen=True)
class NetworkCheckLine:
    name: str
    status: CheckStatus
    detail: str


def _proxy_summary() -> NetworkCheckLine:
    keys = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")
    seen: list[str] = []
    for key in keys:
        value = (os.environ.get(key) or "").strip()
        if value and f"{key}={value}" not in seen:
            seen.append(f"{key}={value}")
    if not seen:
        return NetworkCheckLine(
            name="proxy_env",
            status="warn",
            detail=(
                "No HTTP_PROXY/HTTPS_PROXY/ALL_PROXY set. Browser VPN extensions "
                "do not apply to harnesslab serve — add proxy to ~/.config/harnesslab/env."
            ),
        )
    return NetworkCheckLine(
        name="proxy_env",
        status="ok",
        detail="; ".join(seen),
    )


def _ddgs_check() -> NetworkCheckLine:
    try:
        hits = _search_ddgs(
            query="HarnessLab network check",
            max_results=1,
            timeout_seconds=20.0,
        )
    except ValueError as exc:
        return NetworkCheckLine(name="web_search_ddgs", status="fail", detail=str(exc))
    if hits:
        return NetworkCheckLine(
            name="web_search_ddgs",
            status="ok",
            detail=f"{len(hits)} hit(s); example: {hits[0].url}",
        )
    return NetworkCheckLine(
        name="web_search_ddgs",
        status="warn",
        detail="Connected but parsed zero results.",
    )


def _duckduckgo_check(client: httpx.Client) -> NetworkCheckLine:
    try:
        hits = _search_duckduckgo(client, query="HarnessLab network check", max_results=1)
    except ValueError as exc:
        return NetworkCheckLine(name="duckduckgo_html", status="fail", detail=str(exc))
    except httpx.HTTPError as exc:
        return NetworkCheckLine(
            name="duckduckgo_html",
            status="fail",
            detail=f"HTTP error: {exc}",
        )
    if hits:
        return NetworkCheckLine(
            name="duckduckgo_html",
            status="ok",
            detail=f"{len(hits)} hit(s); example: {hits[0].url}",
        )
    return NetworkCheckLine(
        name="duckduckgo_html",
        status="warn",
        detail="Connected but parsed zero results (anti-bot or empty SERP).",
    )


def _fetch_check(client: httpx.Client, url: str, *, name: str) -> NetworkCheckLine:
    try:
        response = client.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            },
        )
    except httpx.HTTPError as exc:
        return NetworkCheckLine(name=name, status="fail", detail=f"HTTP error: {exc}")
    body = response.text
    snippet = body[:120].replace("\n", " ").strip()
    if name == "fetch_google" and (
        "enablejs" in body.lower() or "consent" in body.lower()[:500]
    ):
        return NetworkCheckLine(
            name=name,
            status="warn",
            detail=(
                f"HTTP {response.status_code}, {len(body)} bytes — JS/consent shell "
                "(expected without browser; do not use Google search URLs with fetch_url)."
            ),
        )
    return NetworkCheckLine(
        name=name,
        status="ok" if response.is_success else "warn",
        detail=f"HTTP {response.status_code}, {len(body)} bytes — {snippet!r}",
    )


def _configured_backend() -> str:
    operator = load_operator_config()
    return (
        os.environ.get("WEB_SEARCH_BACKEND")
        or operator.web_search_backend
        or DEFAULT_WEB_SEARCH_BACKEND
    )


def _backend_check(*, backend: str, api_key: str | None) -> NetworkCheckLine:
    if backend in {"duckduckgo", "ddgs"}:
        if backend == "duckduckgo":
            return NetworkCheckLine(
                name="web_search_duckduckgo",
                status="skip",
                detail="Handled by duckduckgo_html probe.",
            )
        return NetworkCheckLine(
            name="web_search_ddgs",
            status="skip",
            detail="Handled by ddgs probe.",
        )
    if backend == "exa":
        from harnesslab.core.models import ToolCall

        tool = WebSearchTool(backend="exa", max_results=1, api_key=api_key)
        try:
            result = tool.execute(
                ToolCall(name="web_search", args={"query": "HarnessLab network check"})
            )
        finally:
            tool.close()
        mode = "REST" if api_key else "hosted MCP (no key)"
        if result.ok and result.output and result.output != "No results.":
            first_line = result.output.splitlines()[0][:120]
            return NetworkCheckLine(
                name="web_search_exa",
                status="ok",
                detail=f"{mode}: {first_line}",
            )
        if result.error:
            return NetworkCheckLine(
                name="web_search_exa",
                status="fail",
                detail=f"{mode}: {result.error}",
            )
        return NetworkCheckLine(
            name="web_search_exa",
            status="warn",
            detail=f"{mode}: {result.output or 'No results.'}",
        )
    if backend not in {"brave", "tavily", "serpapi"}:
        return NetworkCheckLine(
            name=f"web_search_{backend}",
            status="fail",
            detail=f"Unknown backend {backend!r}",
        )
    if not api_key:
        env_hint = {
            "brave": "BRAVE_API_KEY",
            "tavily": "TAVILY_API_KEY",
            "serpapi": "SERPAPI_API_KEY",
        }[backend]
        return NetworkCheckLine(
            name=f"web_search_{backend}",
            status="skip",
            detail=f"No API key ({env_hint} or WEB_SEARCH_API_KEY); skipping live search test.",
        )
    from harnesslab.core.models import ToolCall

    tool = WebSearchTool(backend=backend, max_results=1, api_key=api_key)
    try:
        result = tool.execute(
            ToolCall(name="web_search", args={"query": "HarnessLab network check"})
        )
    finally:
        tool.close()
    if result.ok and result.output and result.output != "No results.":
        first_line = result.output.splitlines()[0][:120]
        return NetworkCheckLine(
            name=f"web_search_{backend}",
            status="ok",
            detail=first_line,
        )
    if result.error:
        return NetworkCheckLine(
            name=f"web_search_{backend}",
            status="fail",
            detail=result.error,
        )
    return NetworkCheckLine(
        name=f"web_search_{backend}",
        status="warn",
        detail=result.output or "No results.",
    )


def run_network_checks(
    *,
    timeout_seconds: float = 20.0,
    client: httpx.Client | None = None,
) -> list[NetworkCheckLine]:
    """Run connectivity checks used by ``harnesslab check network``."""

    lines: list[NetworkCheckLine] = [_proxy_summary()]
    backend = _configured_backend()
    operator = load_operator_config()
    api_key = resolve_web_search_api_key(
        backend,
        operator.web_search_api_key_env or None,
    )
    lines.append(
        NetworkCheckLine(
            name="web_search_backend",
            status="ok",
            detail=f"backend={backend!r}"
            + (", api_key=set" if api_key else ", api_key=missing"),
        )
    )

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=timeout_seconds, follow_redirects=True)
    assert client is not None
    try:
        if backend == "duckduckgo":
            lines.append(_duckduckgo_check(client))
        elif backend == "ddgs":
            lines.append(_ddgs_check())
        else:
            lines.append(_backend_check(backend=backend, api_key=api_key))
            # Still probe DDG when not default backend — helps diagnose proxy-only fixes.
            try:
                warm = client.get("https://duckduckgo.com/", headers={"User-Agent": "Mozilla/5.0"})
                post = client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": "test", "kl": "wt-wt", "b": ""},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if _duckduckgo_antibot_page(status_code=post.status_code, html=post.text):
                    lines.append(
                        NetworkCheckLine(
                            name="duckduckgo_html",
                            status="warn",
                            detail=(
                                f"Anti-bot page (HTTP {post.status_code}) — expected in CN; "
                                f"using {backend!r} backend instead."
                            ),
                        )
                    )
                else:
                    lines.append(
                        NetworkCheckLine(
                            name="duckduckgo_html",
                            status="ok",
                            detail=f"HTTP {post.status_code}, scrapeable (warm {warm.status_code})",
                        )
                    )
            except httpx.HTTPError as exc:
                lines.append(
                    NetworkCheckLine(
                        name="duckduckgo_html",
                        status="warn",
                        detail=f"Optional probe failed: {exc}",
                    )
                )

        lines.append(
            _fetch_check(client, "https://wttr.in/Beijing?format=3", name="fetch_wttr")
        )
        lines.append(
            _fetch_check(
                client,
                "https://www.google.com/search?q=harnesslab",
                name="fetch_google",
            )
        )
    finally:
        if own_client:
            client.close()

    return lines


def format_network_report(lines: list[NetworkCheckLine]) -> str:
    icon = {"ok": "OK", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}
    out: list[str] = []
    for line in lines:
        out.append(f"[{icon[line.status]:>4}] {line.name}: {line.detail}")
    fails = sum(1 for line in lines if line.status == "fail")
    warns = sum(1 for line in lines if line.status == "warn")
    out.append("")
    if fails:
        out.append(f"Summary: {fails} failure(s), {warns} warning(s).")
    elif warns:
        out.append(f"Summary: all required checks passed; {warns} warning(s).")
    else:
        out.append("Summary: all checks passed.")
    return "\n".join(out)


def network_check_exit_code(lines: list[NetworkCheckLine]) -> int:
    if any(line.status == "fail" for line in lines):
        return 1
    return 0
