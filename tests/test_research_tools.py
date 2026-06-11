"""Tests for Phase 5.1 research tools."""

from __future__ import annotations

from pathlib import Path

import httpx

from harnesslab.core.models import ToolCall
from harnesslab.tools.research_tools import (
    HtmlToMarkdownTool,
    ReadPdfTool,
    WebSearchTool,
    robots_advisory_for_url,
)


def test_web_search_duckduckgo_parses_results() -> None:
    html = """
    <html><body>
      <a class="result__a" href="https://example.com/a">Example A</a>
      <a class="result__snippet" href="https://example.com/a">First snippet</a>
      <a class="result__a" href="https://example.com/b">Example B</a>
      <a class="result__snippet" href="https://example.com/b">Second snippet</a>
    </body></html>
    """

    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        # Home-page warm-up returns a small body; the real search call
        # returns the results HTML.
        if request.url.host == "duckduckgo.com" and request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(200, text=html)

    tool = WebSearchTool(backend="duckduckgo", transport=httpx.MockTransport(handler))
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "example"}))
    finally:
        tool.close()
    assert result.ok, result.error
    assert "Example A" in result.output
    assert "First snippet" in result.output
    assert "https://example.com/a" in result.output

    # The real DDG endpoint requires POST with a real-browser User-Agent.
    search_requests = [r for r in captured_requests if r.url.path == "/html/"]
    assert search_requests, "expected at least one POST to /html/"
    assert search_requests[0].method == "POST"
    ua = search_requests[0].headers.get("User-Agent", "")
    assert "Mozilla/5.0" in ua, "DuckDuckGo blocks default httpx UA"


def test_web_search_duckduckgo_antibot_returns_actionable_error() -> None:
    antibot_html = """
    <!DOCTYPE html><html><head>
      <link rel="canonical" href="https://duckduckgo.com/">
      <title>DuckDuckGo</title>
    </head><body></body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "duckduckgo.com" and request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(202, text=antibot_html)

    tool = WebSearchTool(backend="duckduckgo", transport=httpx.MockTransport(handler))
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "example"}))
    finally:
        tool.close()
    assert not result.ok
    assert result.error is not None
    assert "anti-bot" in result.error.lower()
    assert "HTTPS_PROXY" in result.error


def test_web_search_fallback_backend_uses_secondary_on_primary_failure(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "tavily" in str(request.url):
            calls.append("tavily")
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Tavily Hit",
                            "url": "https://example.com/t",
                            "content": "from tavily",
                        }
                    ]
                },
            )
        calls.append("ddg")
        return httpx.Response(200, text="<html></html>")

    tool = WebSearchTool(
        backend="ddgs",
        fallback_backend="tavily",
        transport=httpx.MockTransport(handler),
    )

    class FailingDDGS:
        def __init__(self, **kwargs: object) -> None:
            pass

        def __enter__(self) -> FailingDDGS:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def text(self, query: str, max_results: int, backend: str) -> list[dict[str, str]]:
            raise RuntimeError("ddgs blocked")

    monkeypatch.setattr("ddgs.DDGS", FailingDDGS)
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "example"}))
    finally:
        tool.close()
    assert result.ok, result.error
    assert "Tavily Hit" in result.output
    assert "fallback backend: tavily" in result.output
    assert calls == ["tavily"]


def test_web_search_tavily_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("WEB_SEARCH_API_KEY", raising=False)
    tool = WebSearchTool(backend="tavily")
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "x"}))
    finally:
        tool.close()
    assert not result.ok
    assert "TAVILY_API_KEY" in (result.error or "")


def test_web_search_ddgs_parses_results(monkeypatch) -> None:
    class FakeDDGS:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> FakeDDGS:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def text(self, query: str, max_results: int, backend: str) -> list[dict[str, str]]:
            assert query == "example"
            assert backend == "duckduckgo"
            return [
                {
                    "title": "DDGS A",
                    "href": "https://example.com/a",
                    "body": "snippet a",
                },
            ]

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    tool = WebSearchTool(backend="ddgs")
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "example"}))
    finally:
        tool.close()
    assert result.ok, result.error
    assert "DDGS A" in result.output
    assert "https://example.com/a" in result.output


def test_web_search_exa_rest_via_tool() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Exa Hit", "url": "https://example.com/exa", "text": "info"},
                ]
            },
        )

    tool = WebSearchTool(
        backend="exa",
        api_key="exa-key",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "test"}))
    finally:
        tool.close()
    assert result.ok, result.error
    assert "Exa Hit" in result.output
    assert "https://example.com/exa" in result.output


def test_web_search_exa_mcp_without_key() -> None:
    payload = (
        '{"result": {"content": [{"type": "text", '
        '"text": "[Page](https://example.com/page)"}]}}'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "exaApiKey" not in str(request.url)
        return httpx.Response(200, text=payload)

    tool = WebSearchTool(backend="exa", transport=httpx.MockTransport(handler))
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "test"}))
    finally:
        tool.close()
    assert result.ok, result.error
    assert "https://example.com/page" in result.output


def test_html_to_markdown_extracts_headings_links_and_lists() -> None:
    tool = HtmlToMarkdownTool()
    result = tool.execute(
        ToolCall(
            name="html_to_markdown",
            args={
                "html": (
                    "<h1>Title</h1><p>Hello <a href='https://example.com'>world</a></p>"
                    "<ul><li>one</li><li>two</li></ul>"
                )
            },
        )
    )
    assert result.ok, result.error
    assert "# Title" in result.output
    assert "[world](https://example.com)" in result.output
    assert "- one" in result.output
    assert "- two" in result.output


def test_read_pdf_uses_injected_extractor(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")

    def fake_extractor(path: Path, *, max_pages: int) -> str:
        assert path == pdf
        assert max_pages == 10
        return "Extracted text."

    tool = ReadPdfTool(tmp_path, extractor=fake_extractor)
    result = tool.execute(
        ToolCall(name="read_pdf", args={"path": "doc.pdf", "max_pages": 10})
    )
    assert result.ok, result.error
    assert result.output == "Extracted text."


def test_read_pdf_rejects_non_pdf_suffix(tmp_path: Path) -> None:
    txt = tmp_path / "notes.txt"
    txt.write_text("hi", encoding="utf-8")
    tool = ReadPdfTool(tmp_path, extractor=lambda _p, *, max_pages: "x")
    result = tool.execute(ToolCall(name="read_pdf", args={"path": "notes.txt"}))
    assert not result.ok
    assert "must end with .pdf" in (result.error or "")


def test_robots_advisory_detects_disallow() -> None:
    robots = "User-agent: *\nDisallow: /private\n"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/robots.txt"
        return httpx.Response(200, text=robots)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        advisory = robots_advisory_for_url(client, "https://example.com/private/data")
    finally:
        client.close()
    assert advisory is not None
    assert "robots advisory" in advisory
