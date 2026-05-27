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


def test_validate_fetch_url_strict_blocks_unknown_host() -> None:
    ok, reason = validate_fetch_url("https://example.com/", mode="strict")
    assert not ok
    assert "allowlist" in reason


def test_validate_fetch_url_open_default_allows_public_host() -> None:
    """Default mode is now ``open`` — public HTTPS hosts must pass."""
    ok, reason = validate_fetch_url("https://example.com/")
    assert ok, reason


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


def test_fetch_url_jina_provider() -> None:
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        assert request.headers.get("Authorization") == "Bearer jina-test"
        return httpx.Response(
            200,
            text="# Article\n\nBody text.",
            headers={"content-type": "text/plain"},
        )

    tool = FetchUrlTool(
        mode="open",
        provider="jina",
        jina_api_key="jina-test",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = tool.execute(
            ToolCall(name="fetch_url", args={"url": "https://example.com/article"})
        )
    finally:
        tool.close()
    assert result.ok, result.error
    assert captured == ["https://r.jina.ai/https://example.com/article"]
    assert "(via Jina Reader)" in result.output
    assert "# Article" in result.output


def test_policy_allows_fetch_url_for_wttr(tmp_path) -> None:
    """Open mode allows public hosts including wttr."""
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, _ = policy.allow_tool(
        ToolCall(name="fetch_url", args={"url": "https://wttr.in/Wangjing?format=3"})
    )
    assert allowed


def test_policy_strict_mode_denies_unlisted_host(tmp_path) -> None:
    """Operators can pin strict mode and keep the allowlist behaviour."""
    policy = DefaultPolicy(workspace_root=tmp_path, fetch_url_mode="strict")
    allowed, reason = policy.allow_tool(
        ToolCall(name="fetch_url", args={"url": "https://evil.example/data"})
    )
    assert not allowed
    assert "allowlist" in reason


def test_policy_open_mode_allows_public_host(tmp_path) -> None:
    """Default policy in open mode must accept arbitrary public HTTPS hosts."""
    policy = DefaultPolicy(workspace_root=tmp_path)
    allowed, _ = policy.allow_tool(
        ToolCall(name="fetch_url", args={"url": "https://github.com/anthropic/sdk"})
    )
    assert allowed


def test_open_mode_blocks_loopback_literal() -> None:
    """SSRF protection: explicit loopback IP must be rejected even in open mode."""
    ok, reason = validate_fetch_url("https://127.0.0.1/internal", mode="open")
    assert not ok
    assert "private" in reason or "loopback" in reason


def test_open_mode_blocks_link_local_metadata() -> None:
    """SSRF protection: cloud-metadata IPv4 address is denied by default deny set."""
    ok, reason = validate_fetch_url("https://169.254.169.254/", mode="open")
    assert not ok
    assert "denylist" in reason or "private" in reason


def test_open_mode_blocks_localhost_hostname() -> None:
    """SSRF protection: ``localhost`` is on the default deny set."""
    ok, reason = validate_fetch_url("https://localhost/health", mode="open")
    assert not ok
    assert "denylist" in reason


def test_open_mode_blocks_private_ipv4() -> None:
    """SSRF protection: RFC 1918 IPv4 literals are rejected."""
    ok, reason = validate_fetch_url("https://10.0.0.5/", mode="open")
    assert not ok
    assert "private" in reason


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
