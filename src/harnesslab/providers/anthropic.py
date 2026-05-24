"""Anthropic provider adapter (Messages API, Post-MVP P3)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx
from anthropic import APIConnectionError, APITimeoutError
from anthropic import APIStatusError as AnthropicAPIStatusError

from harnesslab.core.compaction import ModelOverflowError, estimate_tokens
from harnesslab.core.models import Decision, Session
from harnesslab.core.prompt import ComposedPrompt, PromptBlock, PromptComposer
from harnesslab.providers.catalog import ModelCatalog
from harnesslab.providers.model_resolve import (
    DEFAULT_ANTHROPIC_MODEL,
    resolve_anthropic_model_name,
)
from harnesslab.providers.transforms.anthropic_messages import (
    parse_response,
    serialize_messages,
)
from harnesslab.providers.transports.anthropic_messages import AnthropicMessagesTransport
from harnesslab.telemetry.log import get_logger

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_TOKENS = 8192
DEEPSEEK_ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
_log = get_logger("providers.anthropic")

DynamicBlocksProvider = Callable[[Session], list[PromptBlock]]


def _no_dynamic_blocks(_session: Session) -> list[PromptBlock]:
    return []


class AnthropicModel:
    """ModelPort implementation backed by Anthropic Messages API."""

    def __init__(
        self,
        *,
        tool_specs_provider: Callable[[], list[dict[str, Any]]],
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        thinking_mode: str = "disabled",
        thinking_effort: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        messages_transport: AnthropicMessagesTransport | None = None,
        composer: PromptComposer | None = None,
        dynamic_blocks_provider: DynamicBlocksProvider | None = None,
    ) -> None:
        api_key = _resolve_api_key(api_key, base_url)
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY (or DEEPSEEK_API_KEY with DeepSeek Anthropic base_url) "
                "is required for AnthropicModel. Set it in the environment or pass "
                "api_key explicitly."
            )
        self._tool_specs_provider = tool_specs_provider
        self._base_url = base_url or os.getenv("ANTHROPIC_BASE_URL")
        self._model_name = resolve_anthropic_model_name(model_name=model_name)
        self._thinking_mode = (thinking_mode or "disabled").strip().lower()
        self._thinking_effort = (thinking_effort or "").strip().lower() or None
        self._max_tokens = max_tokens
        self._chat = messages_transport or AnthropicMessagesTransport(
            api_key=api_key,
            base_url=self._base_url,
            timeout_seconds=timeout_seconds,
            httpx_transport=transport,
        )
        self._composer = composer or PromptComposer()
        self._dynamic_blocks_provider = dynamic_blocks_provider or _no_dynamic_blocks
        self._catalog = ModelCatalog()
        self._last_call_meta: dict[str, Any] = {
            "provider": "anthropic",
            "api_family": "anthropic_messages",
            "model_name": self._model_name,
            "base_url": self._base_url,
        }
        self._last_prompt: ComposedPrompt | None = None

    def decide(self, session: Session, user_input: str) -> Decision:
        body = self._request_body(session, user_input)
        prompt_meta = _prompt_meta(self._last_prompt)
        base_meta = {
            "provider": "anthropic",
            "api_family": "anthropic_messages",
            "model_name": self._model_name,
            "thinking_mode": self._thinking_mode,
            "base_url": self._base_url,
            **prompt_meta,
        }
        try:
            payload = self._chat.create_message(body)
        except ModelOverflowError:
            self._last_call_meta = dict(base_meta)
            _log.warning("context overflow model=%s session=%s", self._model_name, session.id)
            raise
        except AnthropicAPIStatusError as exc:
            self._last_call_meta = dict(base_meta)
            _log.warning(
                "API status error model=%s session=%s: %s",
                self._model_name,
                session.id,
                exc,
            )
            return Decision(
                kind="final",
                assistant_message=f"Anthropic request failed: {type(exc).__name__}: {exc}",
            )
        except (APIConnectionError, APITimeoutError, httpx.HTTPError) as exc:
            self._last_call_meta = dict(base_meta)
            _log.warning(
                "transport error model=%s session=%s: %s",
                self._model_name,
                session.id,
                exc,
            )
            return Decision(
                kind="final",
                assistant_message=f"Anthropic request failed: {type(exc).__name__}: {exc}",
            )

        self._last_call_meta = {
            **base_meta,
            **_usage_meta(payload.get("usage")),
        }
        try:
            entry = self._catalog.get(self._model_name)
        except KeyError:
            entry = self._catalog.get(DEFAULT_ANTHROPIC_MODEL)
        turn = parse_response(payload, entry)
        if turn.reasoning_text:
            self._last_call_meta["reasoning_text"] = turn.reasoning_text
        if turn.provider_extra:
            self._last_call_meta["provider_extra"] = turn.provider_extra
        _log.info(
            "model call model=%s session=%s kind=%s tokens=%s",
            self._model_name,
            session.id,
            turn.decision.kind,
            self._last_call_meta.get("total_tokens"),
        )
        return turn.decision

    def last_call_meta(self) -> dict[str, Any]:
        return dict(self._last_call_meta)

    def last_prompt(self) -> ComposedPrompt | None:
        return self._last_prompt

    def _request_body(self, session: Session, user_input: str) -> dict[str, Any]:
        composed = self._composer.build(
            session,
            dynamic_blocks=self._dynamic_blocks_provider(session),
            variables={"model_name": self._model_name},
        )
        self._last_prompt = composed
        try:
            entry = self._catalog.get(self._model_name)
        except KeyError:
            entry = self._catalog.get(DEFAULT_ANTHROPIC_MODEL)
        wire = serialize_messages(composed, session, entry)
        messages = list(wire["messages"])
        if not messages and user_input.strip():
            # Callers that invoke ``decide`` without pre-appending the user turn
            # (e.g. manual smoke tests) still need one user message on the wire.
            messages = [{"role": "user", "content": user_input.strip()}]
        body: dict[str, Any] = {
            "model": self._model_name,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if wire.get("system"):
            body["system"] = wire["system"]
        thinking = _thinking_config(self._thinking_mode)
        if thinking is not None:
            body["thinking"] = thinking
        if self._thinking_effort and self._thinking_mode == "adaptive":
            body["output_config"] = {"effort": self._thinking_effort}
        tools = _anthropic_tools_from_openai(self._tool_specs_provider())
        if tools:
            body["tools"] = tools
            body["tool_choice"] = {"type": "auto"}
        return body


def _thinking_config(mode: str) -> dict[str, Any] | None:
    if mode in {"disabled", "off", "none"}:
        return None
    if mode == "adaptive":
        return {"type": "adaptive"}
    if mode == "enabled":
        return {"type": "enabled", "budget_tokens": 1024}
    return None


def _anthropic_tools_from_openai(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs:
        if spec.get("type") != "function":
            continue
        function = spec.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        description = function.get("description")
        parameters = function.get("parameters")
        out.append(
            {
                "name": name,
                "description": description if isinstance(description, str) else "",
                "input_schema": parameters if isinstance(parameters, dict) else {},
            }
        )
    return out


def _prompt_meta(prompt: ComposedPrompt | None) -> dict[str, Any]:
    if prompt is None:
        return {}
    static_tokens = 0
    dynamic_tokens = 0
    prompt_total = 0
    names: list[str] = []
    for block in prompt.blocks:
        block_tokens = estimate_tokens(block.content)
        prompt_total += block_tokens
        names.append(block.name)
        if block.origin == "static":
            static_tokens += block_tokens
        elif block.origin == "dynamic":
            dynamic_tokens += block_tokens
    return {
        "prompt_tokens_estimate": prompt_total,
        "static_block_tokens": static_tokens,
        "dynamic_block_tokens": dynamic_tokens,
        "prompt_block_names": names,
    }


def _usage_meta(raw_usage: Any) -> dict[str, int]:
    if not isinstance(raw_usage, dict):
        return {}
    out: dict[str, int] = {}
    for src, dst in (
        ("input_tokens", "request_tokens"),
        ("output_tokens", "response_tokens"),
    ):
        value = raw_usage.get(src)
        if isinstance(value, int):
            out[dst] = value
    if "request_tokens" in out and "response_tokens" in out:
        out["total_tokens"] = out["request_tokens"] + out["response_tokens"]
    return out


def _resolve_api_key(api_key: str | None, base_url: str | None) -> str | None:
    if api_key:
        return api_key
    resolved_base = base_url or os.getenv("ANTHROPIC_BASE_URL")
    if _is_deepseek_anthropic_base(resolved_base):
        # DeepSeek Anthropic surface authenticates with DEEPSEEK_API_KEY only.
        ds_key = os.getenv("DEEPSEEK_API_KEY")
        if ds_key:
            return ds_key
    env_key = os.getenv("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    return None


def _is_deepseek_anthropic_base(base_url: str | None) -> bool:
    if not base_url:
        return False
    normalized = base_url.rstrip("/").lower()
    return normalized.endswith("/anthropic") and "deepseek.com" in normalized
