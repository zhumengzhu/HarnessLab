"""Tests for fetch_url tool and policy."""

from __future__ import annotations

import httpx

from harnesslab.core.models import ToolCall
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.tools.fetch_url_tool import (
    FetchUrlTool,
    parse_csv_hosts,
    validate_fetch_url,
)


def test_validate_fetch_url_allows_wttr() -> None:
    ok, _ = validate_fetch_url("https://wttr.in/Beijing?format=3")
    assert ok


def test_validate_fetch_url_blocks_unknown_host() -> None:
    ok, reason = validate_fetch_url("https://example.com/")
    assert not ok
    assert "allowlist" in reason


def test_fetch_url_tool_returns_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "wttr.in" in str(request.url)
        return httpx.Response(200, text="Beijing: ☀️ +25°C")

    tool = FetchUrlTool(transport=httpx.MockTransport(handler))
    try:
        result = tool.execute(
            ToolCall(
                name="fetch_url",
                args={"url": "https://wttr.in/Beijing?format=3"},
            )
        )
    finally:
        tool.close()
    assert result.ok, result.error
    assert "Beijing" in result.output


def test_policy_allows_fetch_url_for_wttr(tmp_path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, _ = policy.allow_tool(
        ToolCall(name="fetch_url", args={"url": "https://wttr.in/Wangjing?format=3"})
    )
    assert allowed


def test_policy_denies_fetch_url_for_unlisted_host(tmp_path) -> None:
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, reason = policy.allow_tool(
        ToolCall(name="fetch_url", args={"url": "https://evil.example/data"})
    )
    assert not allowed
    assert "allowlist" in reason


def test_validate_fetch_url_open_mode_allows_https() -> None:
    ok, reason = validate_fetch_url("https://example.com/path", mode="open")
    assert ok, reason


def test_validate_fetch_url_open_mode_rejects_http() -> None:
    ok, reason = validate_fetch_url("http://example.com/path", mode="open")
    assert not ok
    assert "https" in reason


def test_validate_fetch_url_honors_deny_hosts() -> None:
    ok, reason = validate_fetch_url(
        "https://example.com/path",
        mode="open",
        deny_hosts=frozenset({"example.com"}),
    )
    assert not ok
    assert "denylist" in reason


def test_parse_csv_hosts() -> None:
    hosts = parse_csv_hosts("example.com, wttr.in ,")
    assert hosts == frozenset({"example.com", "wttr.in"})
