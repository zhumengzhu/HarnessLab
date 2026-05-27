"""Tests for Exa search helpers."""

from __future__ import annotations

import httpx

from harnesslab.tools.exa_search import (
    hits_from_exa_mcp_text,
    parse_exa_mcp_response,
    search_exa_mcp,
    search_exa_rest,
)


def test_parse_exa_mcp_response_json() -> None:
    body = (
        '{"result": {"content": [{"type": "text", '
        '"text": "[Example](https://example.com)"}]}}'
    )
    assert parse_exa_mcp_response(body) == "[Example](https://example.com)"


def test_parse_exa_mcp_response_sse() -> None:
    body = (
        'event: message\ndata: {"result": {"content": '
        '[{"type": "text", "text": "hello"}]}}\n\n'
    )
    assert parse_exa_mcp_response(body) == "hello"


def test_hits_from_exa_mcp_text_markdown_links() -> None:
    hits = hits_from_exa_mcp_text(
        "See [Alpha](https://a.test) and [Beta](https://b.test)",
        max_results=5,
    )
    assert len(hits) == 2
    assert hits[0].title == "Alpha"
    assert hits[0].url == "https://a.test"


def test_search_exa_rest_parses_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search")
        assert request.headers["x-api-key"] == "exa-test"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Hit", "url": "https://example.com/h", "text": "snippet"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        hits = search_exa_rest(
            client,
            query="q",
            max_results=3,
            api_key="exa-test",
            api_base_url=None,
        )
    finally:
        client.close()
    assert len(hits) == 1
    assert hits[0].url == "https://example.com/h"


def test_search_exa_mcp_no_key() -> None:
    payload = (
        '{"result": {"content": [{"type": "text", '
        '"text": "1. [Doc](https://docs.example.com/page)"}]}}'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "mcp.exa.ai" in str(request.url)
        assert "exaApiKey" not in str(request.url)
        return httpx.Response(200, text=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        hits = search_exa_mcp(
            client,
            query="docs",
            max_results=5,
            api_base_url=None,
        )
    finally:
        client.close()
    assert hits
    assert hits[0].url == "https://docs.example.com/page"
