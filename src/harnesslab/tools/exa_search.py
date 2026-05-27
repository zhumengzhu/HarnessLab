"""Exa web search via REST API or hosted MCP (OpenCode-compatible)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

import httpx

from harnesslab.tools.research_tools import SearchHit

DEFAULT_EXA_MCP_URL = "https://mcp.exa.ai/mcp"
DEFAULT_EXA_API_BASE = "https://api.exa.ai"

_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
_BARE_URL = re.compile(r"https?://[^\s\)\]>\"']+")


def build_exa_mcp_url(*, api_key: str | None, api_base_url: str | None) -> str:
    """Build Exa hosted MCP URL with optional ``exaApiKey`` query param."""

    base = (api_base_url or DEFAULT_EXA_MCP_URL).rstrip("/")
    if "tools=" not in base:
        base = f"{base}?tools=web_search_exa" if "?" not in base else f"{base}&tools=web_search_exa"
    if api_key:
        sep = "&" if "?" in base else "?"
        base = f"{base}{sep}exaApiKey={quote(api_key, safe='')}"
    return base


def search_exa(
    client: httpx.Client,
    *,
    query: str,
    max_results: int,
    api_key: str | None,
    api_base_url: str | None,
) -> list[SearchHit]:
    """Search with Exa REST when a key is set, else hosted MCP (no key)."""

    key = (api_key or "").strip() or None
    if key:
        return search_exa_rest(
            client,
            query=query,
            max_results=max_results,
            api_key=key,
            api_base_url=api_base_url,
        )
    return search_exa_mcp(
        client,
        query=query,
        max_results=max_results,
        api_base_url=api_base_url,
    )


def search_exa_rest(
    client: httpx.Client,
    *,
    query: str,
    max_results: int,
    api_key: str,
    api_base_url: str | None,
) -> list[SearchHit]:
    base = (api_base_url or DEFAULT_EXA_API_BASE).rstrip("/")
    response = client.post(
        f"{base}/search",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json={
            "query": query,
            "numResults": max_results,
            "type": "auto",
        },
    )
    if response.status_code == 429:
        raise ValueError(
            "Exa API rate limit (HTTP 429). Check EXA_API_KEY quota at "
            "https://dashboard.exa.ai/api-keys"
        )
    response.raise_for_status()
    body = response.json()
    items = body.get("results") if isinstance(body, dict) else []
    hits: list[SearchHit] = []
    if not isinstance(items, list):
        return hits
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        text_value = item.get("text") or item.get("highlight") or item.get("summary")
        snippet = str(text_value).strip() if isinstance(text_value, str) else None
        if title and url:
            hits.append(SearchHit(title=title, url=url, snippet=snippet))
        if len(hits) >= max_results:
            break
    return hits


def search_exa_mcp(
    client: httpx.Client,
    *,
    query: str,
    max_results: int,
    api_base_url: str | None,
) -> list[SearchHit]:
    url = build_exa_mcp_url(api_key=None, api_base_url=api_base_url)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "web_search_exa",
            "arguments": {
                "query": query,
                "type": "auto",
                "numResults": max_results,
                "livecrawl": "fallback",
            },
        },
    }
    response = client.post(
        url,
        json=payload,
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
    )
    if response.status_code == 429:
        raise ValueError(
            "Exa hosted MCP rate limit (HTTP 429). Set EXA_API_KEY in "
            "~/.config/harnesslab/env for your own quota "
            "(https://dashboard.exa.ai/api-keys)."
        )
    response.raise_for_status()
    text = parse_exa_mcp_response(response.text)
    if not text:
        return []
    return hits_from_exa_mcp_text(text, max_results=max_results)


def parse_exa_mcp_response(body: str) -> str | None:
    """Parse JSON or SSE MCP response body into tool text."""

    trimmed = body.strip()
    if trimmed.startswith("{"):
        try:
            data = json.loads(trimmed)
        except json.JSONDecodeError:
            return None
        return extract_mcp_text(data)
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        text = extract_mcp_text(data)
        if text:
            return text
    return None


def extract_mcp_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    content = result.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                return text
    return None


def hits_from_exa_mcp_text(text: str, *, max_results: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for title, url in _MD_LINK.findall(text):
        url = url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        hits.append(SearchHit(title=title.strip(), url=url, snippet=None))
        if len(hits) >= max_results:
            return hits
    for match in _BARE_URL.finditer(text):
        url = match.group(0).rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)
        hits.append(SearchHit(title=url, url=url, snippet=None))
        if len(hits) >= max_results:
            return hits
    if not hits and text.strip():
        hits.append(
            SearchHit(
                title="Exa web search",
                url="",
                snippet=text.strip()[:2000],
            )
        )
    return hits[:max_results]
