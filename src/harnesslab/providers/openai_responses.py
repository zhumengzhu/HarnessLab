"""OpenAI provider adapter (Responses API, Post-MVP P4)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx
from openai import APIConnectionError, APITimeoutError
from openai import APIStatusError as OpenAIAPIStatusError

from harnesslab.core.compaction import ModelOverflowError
from harnesslab.core.context import build_prompt_block_meta
from harnesslab.core.models import Decision, Session
from harnesslab.core.prompt import ComposedPrompt, PromptBlock, PromptComposer
from harnesslab.providers.catalog import ModelCatalog
from harnesslab.providers.model_resolve import (
    DEFAULT_OPENAI_MODEL,
    resolve_openai_model_name,
)
from harnesslab.providers.transforms.openai_responses import parse_response, serialize_request
from harnesslab.providers.transports.openai_responses import OpenAIResponsesTransport
from harnesslab.telemetry.log import get_logger

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_TOKENS = 8192
_log = get_logger("providers.openai")

DynamicBlocksProvider = Callable[[Session], list[PromptBlock]]


def _no_dynamic_blocks(_session: Session) -> list[PromptBlock]:
    return []


class OpenAIResponsesModel:
    """ModelPort implementation backed by OpenAI Responses API."""

    def __init__(
        self,
        *,
        tool_specs_provider: Callable[[], list[dict[str, Any]]],
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        reasoning_effort: str = "none",
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        responses_transport: OpenAIResponsesTransport | None = None,
        composer: PromptComposer | None = None,
        dynamic_blocks_provider: DynamicBlocksProvider | None = None,
    ) -> None:
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for OpenAIResponsesModel. "
                "Set it in the environment or pass api_key explicitly."
            )
        self._tool_specs_provider = tool_specs_provider
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._model_name = resolve_openai_model_name(model_name=model_name)
        self._reasoning_effort = (reasoning_effort or "none").strip().lower()
        self._max_output_tokens = max_output_tokens
        self._chat = responses_transport or OpenAIResponsesTransport(
            api_key=api_key,
            base_url=self._base_url,
            timeout_seconds=timeout_seconds,
            httpx_transport=transport,
        )
        self._composer = composer or PromptComposer()
        self._dynamic_blocks_provider = dynamic_blocks_provider or _no_dynamic_blocks
        self._catalog = ModelCatalog()
        self._last_call_meta: dict[str, Any] = {
            "provider": "openai",
            "api_family": "openai_responses",
            "model_name": self._model_name,
            "base_url": self._base_url,
        }
        self._last_prompt: ComposedPrompt | None = None

    def decide(self, session: Session, user_input: str) -> Decision:
        body = self._request_body(session, user_input)
        prompt_meta = build_prompt_block_meta(
            self._last_prompt.blocks if self._last_prompt else [],
            wire_tool_specs=body.get("tools"),
        )
        base_meta = {
            "provider": "openai",
            "api_family": "openai_responses",
            "model_name": self._model_name,
            "reasoning_effort": self._reasoning_effort,
            "base_url": self._base_url,
            **prompt_meta,
        }
        try:
            payload = self._chat.create_response(body)
        except ModelOverflowError:
            self._last_call_meta = dict(base_meta)
            _log.warning("context overflow model=%s session=%s", self._model_name, session.id)
            raise
        except OpenAIAPIStatusError as exc:
            self._last_call_meta = dict(base_meta)
            _log.warning(
                "API status error model=%s session=%s: %s",
                self._model_name,
                session.id,
                exc,
            )
            return Decision(
                kind="final",
                assistant_message=f"OpenAI request failed: {type(exc).__name__}: {exc}",
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
                assistant_message=f"OpenAI request failed: {type(exc).__name__}: {exc}",
            )

        self._last_call_meta = {
            **base_meta,
            **_usage_meta(payload.get("usage")),
        }
        try:
            entry = self._catalog.get(self._model_name)
        except KeyError:
            entry = self._catalog.get(DEFAULT_OPENAI_MODEL)
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
            entry = self._catalog.get(DEFAULT_OPENAI_MODEL)
        wire = serialize_request(composed, session, entry)
        input_items = list(wire["input"])
        if not input_items and user_input.strip():
            input_items = [{"role": "user", "content": user_input.strip()}]
        body: dict[str, Any] = {
            "model": self._model_name,
            "input": input_items,
            "max_output_tokens": self._max_output_tokens,
        }
        if wire.get("instructions"):
            body["instructions"] = wire["instructions"]
        reasoning = _reasoning_config(self._reasoning_effort)
        if reasoning is not None:
            body["reasoning"] = reasoning
        tools = _responses_tools_from_openai(self._tool_specs_provider())
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body


def _reasoning_config(effort: str) -> dict[str, str] | None:
    if effort in {"none", "off", "disabled"}:
        return None
    if effort in {"low", "medium", "high", "xhigh", "max"}:
        return {"effort": effort}
    return None


def _responses_tools_from_openai(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "type": "function",
                "name": name,
                "description": description if isinstance(description, str) else "",
                "parameters": parameters if isinstance(parameters, dict) else {},
                "strict": False,
            }
        )
    return out


def _usage_meta(raw_usage: Any) -> dict[str, int]:
    if not isinstance(raw_usage, dict):
        return {}
    out: dict[str, int] = {}
    for src, dst in (
        ("input_tokens", "request_tokens"),
        ("output_tokens", "response_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = raw_usage.get(src)
        if isinstance(value, int):
            out[dst] = value
    details = raw_usage.get("output_tokens_details")
    if isinstance(details, dict):
        reasoning = details.get("reasoning_tokens")
        if isinstance(reasoning, int):
            out["reasoning_tokens"] = reasoning
    if "total_tokens" not in out and "request_tokens" in out and "response_tokens" in out:
        out["total_tokens"] = out["request_tokens"] + out["response_tokens"]
    return out
