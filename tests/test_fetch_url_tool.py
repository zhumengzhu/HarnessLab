"""Tests for fetch_url tool and policy."""

from __future__ import annotations

import httpx

from harnesslab.core.models import ToolCall
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.tools.fetch_url_tool import FetchUrlTool, validate_fetch_url


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
