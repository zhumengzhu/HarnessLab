"""Tests for web research API key resolution and network diagnostics."""

from __future__ import annotations

import httpx

from harnesslab.diagnostics.network_check import (
    format_network_report,
    network_check_exit_code,
    run_network_checks,
)
from harnesslab.tools.research_tools import resolve_web_search_api_key


def test_resolve_web_search_api_key_prefers_backend_specific(monkeypatch) -> None:
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "generic")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-specific")
    assert resolve_web_search_api_key("tavily", None) == "tvly-specific"
    assert resolve_web_search_api_key("brave", None) == "generic"


def test_resolve_web_search_api_key_honors_configured_env(monkeypatch) -> None:
    monkeypatch.setenv("MY_SEARCH_KEY", "from-config")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert resolve_web_search_api_key("tavily", "MY_SEARCH_KEY") == "from-config"


def test_network_check_duckduckgo_antibot_is_fail(monkeypatch) -> None:
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("WEB_SEARCH_BACKEND", raising=False)
    monkeypatch.setenv("WEB_SEARCH_BACKEND", "duckduckgo")

    antibot = """
    <!DOCTYPE html><html><head>
      <link rel="canonical" href="https://duckduckgo.com/">
      <title>DuckDuckGo</title>
    </head><body></body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "duckduckgo.com" in str(request.url):
            return httpx.Response(202, text=antibot)
        if "wttr.in" in str(request.url):
            return httpx.Response(200, text="Beijing: ☀ +25°C")
        if "google.com" in str(request.url):
            return httpx.Response(200, text="<html>enablejs please</html>")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, follow_redirects=True, timeout=5.0)
    try:
        lines = run_network_checks(timeout_seconds=5.0, client=client)
    finally:
        client.close()
    report = format_network_report(lines)
    assert "duckduckgo_html" in report
    assert network_check_exit_code(lines) == 1
