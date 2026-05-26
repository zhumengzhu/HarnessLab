"""DeepSeek provider adapter (OpenAI-compatible chat completions API)."""

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
from harnesslab.core.stream_context import emit_stream_delta, stream_sink_active
from harnesslab.providers.catalog import ModelCatalog
from harnesslab.providers.model_resolve import (
    DEFAULT_DEEPSEEK_MODEL,
    resolve_deepseek_model_name,
)
from harnesslab.providers.transforms.openai_chat import parse_response, serialize_messages
from harnesslab.providers.transports.openai_chat import OpenAIChatTransport
from harnesslab.telemetry.log import get_logger

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_log = get_logger("providers.deepseek")
# Official API models (2026): deepseek-v4-flash, deepseek-v4-pro.
# deepseek-chat → v4-flash non-thinking (deprecated alias).
DEFAULT_MODEL = DEFAULT_DEEPSEEK_MODEL
SUPPORTED_API_MODELS: frozenset[str] = frozenset(
    {
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-chat",
        "deepseek-reasoner",
    }
)
DEFAULT_TIMEOUT_SECONDS = 30.0

DynamicBlocksProvider = Callable[[Session], list[PromptBlock]]


def _no_dynamic_blocks(_session: Session) -> list[PromptBlock]:
    return []


class DeepSeekModel:
    """ModelPort implementation backed by DeepSeek Chat Completions.

    The prompt sent to DeepSeek is assembled by :class:`PromptComposer`:
    packaged static blocks, optional dynamic blocks supplied per call
    (env / agents_md / tool_guide — wired by the CLI), then the
    session's conversation messages. The model_name placeholder in the
    identity block is substituted with the live model name.
    """

    def __init__(
        self,
        *,
        tool_specs_provider: Callable[[], list[dict[str, Any]]],
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        thinking_mode: str = "disabled",
        reasoning_effort: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        chat_transport: OpenAIChatTransport | None = None,
        composer: PromptComposer | None = None,
        dynamic_blocks_provider: DynamicBlocksProvider | None = None,
    ) -> None:
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is required for DeepSeekModel. "
                "Set it in the environment or pass api_key explicitly."
            )
        self._tool_specs_provider = tool_specs_provider
        self._base_url = base_url or os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL
        self._model_name = resolve_deepseek_model_name(model_name=model_name)
        self._thinking_mode = (thinking_mode or "disabled").strip().lower()
        self._reasoning_effort = (
            (reasoning_effort or "").strip().lower() or None
            if self._thinking_mode == "enabled"
            else None
        )
        self._chat = chat_transport or OpenAIChatTransport(
            api_key=api_key,
            base_url=self._base_url,
            timeout_seconds=timeout_seconds,
            httpx_transport=transport,
        )
        self._composer = composer or PromptComposer()
        self._dynamic_blocks_provider = dynamic_blocks_provider or _no_dynamic_blocks
        self._catalog = ModelCatalog()
        self._last_call_meta: dict[str, Any] = {
            "provider": "deepseek",
            "model_name": self._model_name,
        }
        self._last_prompt: ComposedPrompt | None = None

    def decide(self, session: Session, user_input: str) -> Decision:
        body = self._request_body(session)
        prompt_meta = build_prompt_block_meta(
            self._last_prompt.blocks if self._last_prompt else [],
            wire_tool_specs=body.get("tools"),
        )
        base_meta = {
            "provider": "deepseek",
            "model_name": self._model_name,
            **prompt_meta,
        }
        try:
            if stream_sink_active():
                payload = self._chat.create_chat_completion_stream(
                    body,
                    on_delta=lambda kind, text: emit_stream_delta(
                        "reasoning" if kind == "reasoning" else "assistant", text
                    ),
                )
            else:
                payload = self._chat.create_chat_completion(body)
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
                assistant_message=f"DeepSeek request failed: {type(exc).__name__}: {exc}",
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
                assistant_message=f"DeepSeek request failed: {type(exc).__name__}: {exc}",
            )

        self._last_call_meta = {
            **base_meta,
            **_usage_meta(payload.get("usage")),
        }
        turn = parse_response(payload)
        if turn.reasoning_text:
            self._last_call_meta["reasoning_text"] = turn.reasoning_text
        _log.info(
            "model call model=%s session=%s kind=%s tokens=%s",
            self._model_name,
            session.id,
            turn.decision.kind,
            self._last_call_meta.get("total_tokens"),
        )
        if turn.reasoning_text:
            _log.debug(
                "reasoning captured session=%s chars=%s",
                session.id,
                len(turn.reasoning_text),
            )
        return turn.decision

    def last_call_meta(self) -> dict[str, Any]:
        return dict(self._last_call_meta)

    def last_prompt(self) -> ComposedPrompt | None:
        """Return the most recently composed prompt for inspection.

        The Phase 2.6 context inspector calls this so the CLI can show
        the exact block breakdown that produced the last model call.
        """

        return self._last_prompt

    def _request_body(self, session: Session) -> dict[str, Any]:
        composed = self._composer.build(
            session,
            dynamic_blocks=self._dynamic_blocks_provider(session),
            variables={"model_name": self._model_name},
        )
        self._last_prompt = composed
        try:
            entry = self._catalog.get(self._model_name)
        except KeyError:
            entry = self._catalog.get(DEFAULT_DEEPSEEK_MODEL)
        body: dict[str, Any] = {
            "model": self._model_name,
            "messages": serialize_messages(composed, session, entry),
        }
        if self._thinking_mode == "disabled":
            body["thinking"] = {"type": "disabled"}
        else:
            body["thinking"] = {"type": "enabled"}
            body["reasoning_effort"] = self._reasoning_effort or "high"
        tools = self._tool_specs_provider()
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body


def _decision_from_payload(payload: dict[str, Any]) -> Decision:
    """Backward-compatible wrapper around :func:`parse_response`."""

    return parse_response(payload).decision


def _usage_meta(raw_usage: Any) -> dict[str, int]:
    if not isinstance(raw_usage, dict):
        return {}
    out: dict[str, int] = {}
    for src, dst in (
        ("prompt_tokens", "request_tokens"),
        ("completion_tokens", "response_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = raw_usage.get(src)
        if isinstance(value, int):
            out[dst] = value
    return out


def tool_specs_from_registry(registry_tools: list[Any]) -> list[dict[str, Any]]:
    """Build OpenAI-compatible tools spec from ToolPort instances."""

    specs: list[dict[str, Any]] = []
    for tool in registry_tools:
        name = getattr(tool, "name", None)
        description = getattr(tool, "description", "")
        args_schema = getattr(tool, "args_schema", {})
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(description, str):
            description = ""
        if not isinstance(args_schema, dict):
            args_schema = {}
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": args_schema,
                },
            }
        )
    return specs
