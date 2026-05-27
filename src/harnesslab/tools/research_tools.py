"""Web/research-oriented tools (Phase 5.1)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import ToolCall, ToolResult

DEFAULT_WEB_SEARCH_BACKEND = "ddgs"
DEFAULT_WEB_SEARCH_MAX_RESULTS = 5
DEFAULT_WEB_SEARCH_TIMEOUT_SECONDS = 15.0

_BACKEND_API_KEY_ENVS: dict[str, str] = {
    "brave": "BRAVE_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "serpapi": "SERPAPI_API_KEY",
    "exa": "EXA_API_KEY",
}


def resolve_web_search_api_key(
    backend: str,
    configured_api_key_env: str | None,
) -> str | None:
    """Resolve the API key for a paid ``web_search`` backend."""

    normalized = backend.strip().lower()
    generic = (os.environ.get("WEB_SEARCH_API_KEY") or "").strip() or None
    if configured_api_key_env:
        configured = (os.environ.get(configured_api_key_env) or "").strip()
        if configured:
            return configured
    env_name = _BACKEND_API_KEY_ENVS.get(normalized)
    if env_name:
        specific = (os.environ.get(env_name) or "").strip()
        if specific:
            return specific
    return generic

_TEXTLIKE_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml+xml",
    "application/javascript",
)


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str | None = None


class WebSearchTool:
    """Search web results via a configurable backend."""

    name = "web_search"
    description = (
        "Search the web and return concise result hits. "
        "Backend is selected by operator config or WEB_SEARCH_BACKEND."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query text.",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "Max number of result hits to return (default: 5).",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        backend: str = DEFAULT_WEB_SEARCH_BACKEND,
        max_results: int = DEFAULT_WEB_SEARCH_MAX_RESULTS,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = DEFAULT_WEB_SEARCH_TIMEOUT_SECONDS,
        api_key: str | None = None,
        api_base_url: str | None = None,
    ) -> None:
        self._backend = backend.strip().lower() or DEFAULT_WEB_SEARCH_BACKEND
        self._max_results = max(1, min(max_results, 20))
        self._api_key = (api_key or "").strip() or None
        self._api_base_url = (api_base_url or "").strip() or None
        self._timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def execute(self, call: ToolCall) -> ToolResult:
        query = str(call.args.get("query", "")).strip()
        if not query:
            return ToolResult(ok=False, output="", error="missing query")
        max_results = _coerce_max_results(call.args.get("max_results"), self._max_results)
        try:
            hits = self._search(query=query, max_results=max_results)
        except ValueError as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, output="", error=f"web_search failed: {exc}")
        if not hits:
            return ToolResult(ok=True, output="No results.")
        lines = []
        for idx, hit in enumerate(hits, start=1):
            snippet = f"\n   {hit.snippet}" if hit.snippet else ""
            lines.append(f"{idx}. {hit.title}\n   {hit.url}{snippet}")
        return ToolResult(ok=True, output="\n".join(lines))

    def _search(self, *, query: str, max_results: int) -> list[SearchHit]:
        backend = self._backend
        if backend == "ddgs":
            return _search_ddgs(
                query=query,
                max_results=max_results,
                timeout_seconds=self._timeout_seconds,
            )
        if backend == "duckduckgo":
            return _search_duckduckgo(self._client, query=query, max_results=max_results)
        if backend == "brave":
            return _search_brave(
                self._client,
                query=query,
                max_results=max_results,
                api_key=self._required_api_key("BRAVE_API_KEY"),
                api_base_url=self._api_base_url,
            )
        if backend == "tavily":
            return _search_tavily(
                self._client,
                query=query,
                max_results=max_results,
                api_key=self._required_api_key("TAVILY_API_KEY"),
                api_base_url=self._api_base_url,
            )
        if backend == "serpapi":
            return _search_serpapi(
                self._client,
                query=query,
                max_results=max_results,
                api_key=self._required_api_key("SERPAPI_API_KEY"),
                api_base_url=self._api_base_url,
            )
        if backend == "exa":
            from harnesslab.tools.exa_search import search_exa

            return search_exa(
                self._client,
                query=query,
                max_results=max_results,
                api_key=self._optional_api_key("EXA_API_KEY"),
                api_base_url=self._api_base_url,
            )
        raise ValueError(
            f"unknown web_search backend {self._backend!r} "
            "(known: ddgs, duckduckgo, brave, tavily, serpapi, exa)"
        )

    def _optional_api_key(self, env_name: str) -> str | None:
        if self._api_key:
            return self._api_key
        specific = (os.environ.get(env_name) or "").strip()
        if specific:
            return specific
        generic = (os.environ.get("WEB_SEARCH_API_KEY") or "").strip()
        return generic or None

    def _required_api_key(self, env_name: str) -> str:
        if self._api_key:
            return self._api_key
        specific = (os.environ.get(env_name) or "").strip()
        if specific:
            return specific
        generic = (os.environ.get("WEB_SEARCH_API_KEY") or "").strip()
        if generic:
            return generic
        raise ValueError(
            f"{env_name} is required for web_search backend {self._backend!r}"
        )


class HtmlToMarkdownTool:
    """Convert HTML to readable markdown-like text."""

    name = "html_to_markdown"
    description = (
        "Convert HTML content into markdown-like plain text preserving "
        "headings, links, paragraphs, and list items."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": "Raw HTML text to convert.",
            },
        },
        "required": ["html"],
        "additionalProperties": False,
    }

    def __init__(self, *, limits: RuntimeLimits | None = None) -> None:
        self._limits = limits or RuntimeLimits()

    def execute(self, call: ToolCall) -> ToolResult:
        html = str(call.args.get("html", ""))
        if not html.strip():
            return ToolResult(ok=False, output="", error="missing html")
        parser = _MarkdownishParser()
        parser.feed(html)
        text = parser.as_text()
        return ToolResult(ok=True, output=_cap_output(text, self._limits.output_bytes_cap))


class ReadPdfTool:
    """Extract readable text from a PDF inside the workspace."""

    name = "read_pdf"
    description = (
        "Extract UTF-8 text from a workspace PDF file. "
        "Useful for research/notes ingestion."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative PDF path.",
            },
            "max_pages": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "description": "Optional cap on extracted pages (default: 50).",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        workspace_root: Path,
        *,
        limits: RuntimeLimits | None = None,
        extractor: Any | None = None,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._limits = limits or RuntimeLimits()
        self._extractor = extractor or _extract_pdf_text

    def execute(self, call: ToolCall) -> ToolResult:
        raw_path = str(call.args.get("path", "")).strip()
        if not raw_path:
            return ToolResult(ok=False, output="", error="missing path")
        candidate = (self._workspace_root / raw_path).resolve()
        try:
            candidate.relative_to(self._workspace_root)
        except ValueError:
            return ToolResult(ok=False, output="", error="path out of workspace")
        if candidate.suffix.lower() != ".pdf":
            return ToolResult(ok=False, output="", error="path must end with .pdf")
        if not candidate.exists():
            return ToolResult(ok=False, output="", error=f"file not found: {raw_path}")
        max_pages = _coerce_max_pages(call.args.get("max_pages"))
        try:
            text = self._extractor(candidate, max_pages=max_pages)
        except Exception as exc:
            return ToolResult(ok=False, output="", error=f"read_pdf failed: {exc}")
        return ToolResult(ok=True, output=_cap_output(text, self._limits.output_bytes_cap))


class _MarkdownishParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._in_title = False
        self._in_script = False
        self._in_style = False
        self._in_link = False
        self._link_href: str | None = None
        self._link_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in {"script", "style"}:
            if t == "script":
                self._in_script = True
            if t == "style":
                self._in_style = True
            return
        if t in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n" + "#" * int(t[1]) + " ")
            self._in_title = True
            return
        if t == "p":
            self._parts.append("\n\n")
            return
        if t == "br":
            self._parts.append("\n")
            return
        if t == "li":
            self._parts.append("\n- ")
            return
        if t == "a":
            self._in_link = True
            self._link_text_parts.clear()
            attrs_dict = {k.lower(): v for k, v in attrs}
            self._link_href = attrs_dict.get("href")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "script":
            self._in_script = False
            return
        if t == "style":
            self._in_style = False
            return
        if t in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._in_title = False
            self._parts.append("\n")
            return
        if t == "a" and self._in_link:
            link_text = _normalize_space("".join(self._link_text_parts))
            href = (self._link_href or "").strip()
            if link_text and href:
                self._parts.append(f"[{link_text}]({href})")
            elif link_text:
                self._parts.append(link_text)
            self._in_link = False
            self._link_href = None
            self._link_text_parts.clear()

    def handle_data(self, data: str) -> None:
        if self._in_script or self._in_style:
            return
        text = _normalize_space(unescape(data))
        if not text:
            return
        if self._in_link:
            self._link_text_parts.append(text)
            return
        self._parts.append(text)

    def as_text(self) -> str:
        text = "".join(self._parts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()


_DDG_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) "
    "Gecko/20100101 Firefox/131.0"
)
_DDG_HEADERS = {
    "User-Agent": _DDG_USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
    "Origin": "https://duckduckgo.com",
    "Referer": "https://duckduckgo.com/",
}


def _duckduckgo_antibot_page(*, status_code: int, html: str) -> bool:
    """Return True when DDG served the JS-only anti-bot shell instead of results."""

    if status_code == 202:
        return True
    if "result__a" in html:
        return False
    lowered = html.lower()
    return (
        'rel="canonical" href="https://duckduckgo.com/"' in lowered
        or "<title>\n        duckduckgo\n    </title>" in lowered
    )


def _duckduckgo_blocked_message() -> str:
    return (
        "DuckDuckGo HTML search returned an anti-bot page (HTTP 202 or empty "
        "results). This is common from mainland China or when the process "
        "does not use your VPN proxy. Fixes: (1) add "
        "HTTPS_PROXY=http://127.0.0.1:<port> to ~/.config/harnesslab/env "
        "(match your Clash/Surge local port), restart ./hl-serve; (2) switch "
        "tools.web_search.backend to ddgs, exa, tavily, brave, or serpapi "
        "(exa works without a key via hosted MCP; set EXA_API_KEY for quota)."
    )


def _search_ddgs(*, query: str, max_results: int, timeout_seconds: float) -> list[SearchHit]:
    """Search via the ``ddgs`` metasearch library (DeerFlow-style default)."""

    try:
        from ddgs import DDGS
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "web_search backend 'ddgs' requires the ddgs package (uv sync)"
        ) from exc
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "").strip() or None
    try:
        with DDGS(timeout=timeout_seconds, proxy=proxy) as ddgs:
            rows = ddgs.text(query, max_results=max_results, backend="duckduckgo")
    except Exception as exc:
        raise ValueError(f"ddgs search failed: {exc}") from exc
    hits: list[SearchHit] = []
    if not isinstance(rows, list):
        return hits
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).strip()
        url = str(row.get("href", row.get("url", ""))).strip()
        body = row.get("body", row.get("snippet"))
        snippet = str(body).strip() if isinstance(body, str) and body.strip() else None
        if title and url:
            hits.append(SearchHit(title=title, url=url, snippet=snippet))
        if len(hits) >= max_results:
            break
    return hits


def _search_duckduckgo(client: httpx.Client, *, query: str, max_results: int) -> list[SearchHit]:
    # ``html.duckduckgo.com`` returns scrapeable result rows when called
    # via POST with a real browser User-Agent; bare GET on
    # ``duckduckgo.com/html`` is anti-bot blocked (status 202 + JS-only
    # home page). The home-page warm-up establishes the session cookies
    # that DDG sometimes requires before serving results.
    base = "https://html.duckduckgo.com/html/"
    try:
        client.get(
            "https://duckduckgo.com/",
            headers=_DDG_HEADERS,
        )
    except httpx.HTTPError:
        pass
    response = client.post(
        base,
        data={"q": query, "kl": "wt-wt", "b": ""},
        headers=_DDG_HEADERS,
    )
    response.raise_for_status()
    html = response.text
    if _duckduckgo_antibot_page(status_code=response.status_code, html=html):
        raise ValueError(_duckduckgo_blocked_message())
    pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippets = [_strip_html(s) for s in snippet_pattern.findall(html)]
    hits: list[SearchHit] = []
    for idx, (href, title_html) in enumerate(pattern.findall(html)):
        clean_title = _strip_html(title_html)
        resolved_url = _decode_duckduckgo_redirect(href)
        if not clean_title or not resolved_url:
            continue
        snippet = snippets[idx] if idx < len(snippets) else None
        hits.append(SearchHit(title=clean_title, url=resolved_url, snippet=snippet))
        if len(hits) >= max_results:
            break
    return hits


def _search_brave(
    client: httpx.Client,
    *,
    query: str,
    max_results: int,
    api_key: str,
    api_base_url: str | None,
) -> list[SearchHit]:
    base = (api_base_url or "https://api.search.brave.com").rstrip("/")
    response = client.get(
        f"{base}/res/v1/web/search",
        params={"q": query, "count": max_results},
        headers={"X-Subscription-Token": api_key},
    )
    response.raise_for_status()
    body = response.json()
    items = ((body.get("web") or {}).get("results") or []) if isinstance(body, dict) else []
    return _hits_from_items(items, title_key="title", url_key="url", snippet_key="description")


def _search_tavily(
    client: httpx.Client,
    *,
    query: str,
    max_results: int,
    api_key: str,
    api_base_url: str | None,
) -> list[SearchHit]:
    base = (api_base_url or "https://api.tavily.com").rstrip("/")
    response = client.post(
        f"{base}/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
        },
    )
    response.raise_for_status()
    body = response.json()
    items = body.get("results") if isinstance(body, dict) else []
    return _hits_from_items(items, title_key="title", url_key="url", snippet_key="content")


def _search_serpapi(
    client: httpx.Client,
    *,
    query: str,
    max_results: int,
    api_key: str,
    api_base_url: str | None,
) -> list[SearchHit]:
    base = (api_base_url or "https://serpapi.com").rstrip("/")
    response = client.get(
        f"{base}/search.json",
        params={
            "q": query,
            "engine": "google",
            "api_key": api_key,
            "num": max_results,
        },
    )
    response.raise_for_status()
    body = response.json()
    items = body.get("organic_results") if isinstance(body, dict) else []
    return _hits_from_items(items, title_key="title", url_key="link", snippet_key="snippet")


def _hits_from_items(
    items: object,
    *,
    title_key: str,
    url_key: str,
    snippet_key: str,
) -> list[SearchHit]:
    if not isinstance(items, list):
        return []
    out: list[SearchHit] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get(title_key, "")).strip()
        url = str(item.get(url_key, "")).strip()
        snippet_value = item.get(snippet_key)
        snippet = str(snippet_value).strip() if isinstance(snippet_value, str) else None
        if title and url:
            out.append(SearchHit(title=title, url=url, snippet=snippet))
    return out


def _decode_duckduckgo_redirect(href: str) -> str:
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        encoded = parse_qs(parsed.query).get("uddg", [])
        if encoded:
            return encoded[0]
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return ""


def _extract_pdf_text(path: Path, *, max_pages: int) -> str:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pypdfium2 is required for read_pdf tool") from exc

    doc = pdfium.PdfDocument(str(path))
    page_count = min(len(doc), max_pages)
    parts: list[str] = []
    for index in range(page_count):
        page = doc[index]
        textpage = page.get_textpage()
        parts.append(textpage.get_text_range())
        textpage.close()
        page.close()
    doc.close()
    text = "\n\n".join(part.strip() for part in parts if part.strip())
    return text or "(no extractable text)"


def _coerce_max_results(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, 20))


def _coerce_max_pages(value: object) -> int:
    if value is None:
        return 50
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 50
    return max(1, min(n, 500))


def _strip_html(text: str) -> str:
    stripped = re.sub(r"<[^>]+>", "", text)
    return _normalize_space(unescape(stripped))


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _cap_output(text: str, cap_bytes: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= cap_bytes:
        return text
    return data[:cap_bytes].decode("utf-8", errors="replace") + "\n(truncated)"


def is_textlike_content_type(content_type: str | None) -> bool:
    if not content_type:
        return True
    ctype = content_type.split(";", 1)[0].strip().lower()
    return any(ctype.startswith(prefix) for prefix in _TEXTLIKE_CONTENT_TYPES)


def robots_advisory_for_url(client: httpx.Client, url: str) -> str | None:
    """Return advisory text when robots policy appears to disallow the URL path."""

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = client.get(robots_url)
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    disallowed = _robots_disallow_paths(response.text)
    path = parsed.path or "/"
    if any(path.startswith(prefix) for prefix in disallowed):
        return (
            "robots advisory: target path appears disallowed for User-agent * "
            f"by {robots_url}"
        )
    return None


def _robots_disallow_paths(robots_text: str) -> list[str]:
    ua_star = False
    out: list[str] = []
    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        k = key.strip().lower()
        v = value.strip()
        if k == "user-agent":
            ua_star = v == "*"
            continue
        if ua_star and k == "disallow" and v:
            out.append(v)
    return out


def safe_query_for_backend(query: str) -> str:
    return quote_plus(query, safe="")
