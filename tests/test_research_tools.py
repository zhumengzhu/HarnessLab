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
      <a class="result__a" href="https://example.com/b">Example B</a>
    </body></html>
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    tool = WebSearchTool(backend="duckduckgo", transport=httpx.MockTransport(handler))
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "example"}))
    finally:
        tool.close()
    assert result.ok, result.error
    assert "Example A" in result.output
    assert "https://example.com/a" in result.output


def test_web_search_tavily_requires_key() -> None:
    tool = WebSearchTool(backend="tavily")
    try:
        result = tool.execute(ToolCall(name="web_search", args={"query": "x"}))
    finally:
        tool.close()
    assert not result.ok
    assert "TAVILY_API_KEY" in (result.error or "")


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
