"""Google Gemini provider adapter (generateContent, Post-MVP P5)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from google.genai import errors as genai_errors

from harnesslab.core.compaction import ModelOverflowError, estimate_tokens
from harnesslab.core.context import build_prompt_block_meta
from harnesslab.core.models import Decision, Session
from harnesslab.core.prompt import ComposedPrompt, PromptBlock, PromptComposer
from harnesslab.providers.catalog import CatalogEntry, ModelCatalog
from harnesslab.providers.model_resolve import (
    DEFAULT_GEMINI_MODEL,
    resolve_gemini_model_name,
)
from harnesslab.providers.transforms.google_generate_content import (
    parse_response,
    serialize_request,
)
from harnesslab.providers.transports.google_genai import GoogleGenAITransport
from harnesslab.telemetry.log import get_logger

DEFAULT_TIMEOUT_SECONDS = 30.0
_log = get_logger("providers.gemini")

DynamicBlocksProvider = Callable[[Session], list[PromptBlock]]


def _no_dynamic_blocks(_session: Session) -> list[PromptBlock]:
    return []


class GeminiModel:
    """ModelPort implementation backed by Google Gemini generateContent."""

    def __init__(
        self,
        *,
        tool_specs_provider: Callable[[], list[dict[str, Any]]],
        api_key: str | None = None,
        model_name: str | None = None,
        thinking_budget: int | None = None,
        thinking_level: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        genai_transport: GoogleGenAITransport | None = None,
        composer: PromptComposer | None = None,
        dynamic_blocks_provider: DynamicBlocksProvider | None = None,
    ) -> None:
        api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY (or GEMINI_API_KEY) is required for GeminiModel. "
                "Set it in the environment or pass api_key explicitly."
            )
        self._tool_specs_provider = tool_specs_provider
        self._model_name = resolve_gemini_model_name(model_name=model_name)
        self._thinking_budget = thinking_budget
        self._thinking_level = (thinking_level or "").strip().lower() or None
        self._chat = genai_transport or GoogleGenAITransport(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        self._composer = composer or PromptComposer()
        self._dynamic_blocks_provider = dynamic_blocks_provider or _no_dynamic_blocks
        self._catalog = ModelCatalog()
        self._last_call_meta: dict[str, Any] = {
            "provider": "google",
            "api_family": "google_generate_content",
            "model_name": self._model_name,
        }
        self._last_prompt: ComposedPrompt | None = None

    def decide(self, session: Session, user_input: str) -> Decision:
        body = self._request_body(session, user_input)
        prompt_meta = build_prompt_block_meta(
            self._last_prompt.blocks if self._last_prompt else [],
            wire_tool_specs=body.get("tools"),
        )
        entry = _catalog_entry(self._catalog, self._model_name)
        base_meta = {
            "provider": "google",
            "api_family": "google_generate_content",
            "model_name": self._model_name,
            "thinking_schema": entry.thinking_schema,
            **prompt_meta,
        }
        try:
            payload = self._chat.generate_content(body)
        except ModelOverflowError:
            self._last_call_meta = dict(base_meta)
            _log.warning("context overflow model=%s session=%s", self._model_name, session.id)
            raise
        except genai_errors.APIError as exc:
            self._last_call_meta = dict(base_meta)
            _log.warning(
                "API error model=%s session=%s: %s",
                self._model_name,
                session.id,
                exc,
            )
            return Decision(
                kind="final",
                assistant_message=f"Gemini request failed: {type(exc).__name__}: {exc}",
            )

        self._last_call_meta = {
            **base_meta,
            **_usage_meta(payload.get("usageMetadata") or payload.get("usage_metadata")),
        }
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
        entry = _catalog_entry(self._catalog, self._model_name)
        wire = serialize_request(composed, session, entry)
        contents = list(wire["contents"])
        if not contents and user_input.strip():
            contents = [{"role": "user", "parts": [{"text": user_input.strip()}]}]
        body: dict[str, Any] = {
            "model": self._model_name,
            "contents": contents,
        }
        if wire.get("system_instruction"):
            body["system_instruction"] = wire["system_instruction"]
        thinking_config = _thinking_config(
            entry,
            thinking_budget=self._thinking_budget,
            thinking_level=self._thinking_level,
        )
        if thinking_config:
            body["thinking_config"] = thinking_config
        tools = _gemini_tools_from_openai(self._tool_specs_provider())
        if tools:
            body["tools"] = tools
        _maybe_warn_context_size(composed, entry)
        return body


def _catalog_entry(catalog: ModelCatalog, model_name: str) -> CatalogEntry:
    try:
        return catalog.get(model_name)
    except KeyError:
        return catalog.get(DEFAULT_GEMINI_MODEL)


def _thinking_config(
    entry: CatalogEntry,
    *,
    thinking_budget: int | None,
    thinking_level: str | None,
) -> dict[str, Any] | None:
    schema = entry.thinking_schema
    if schema == "budget":
        budget = thinking_budget
        if budget is None:
            budget = -1 if entry.thinking_default == "dynamic" else 0
        return {"thinking_budget": budget}
    if schema == "level":
        level = thinking_level or entry.thinking_default or "low"
        return {"thinking_level": level}
    return None


def _gemini_tools_from_openai(specs: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    declarations: list[dict[str, Any]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        function = spec.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        decl: dict[str, Any] = {
            "name": name,
            "description": function.get("description") or "",
        }
        parameters = function.get("parameters")
        if isinstance(parameters, dict):
            decl["parameters"] = parameters
        declarations.append(decl)
    if not declarations:
        return None
    return [{"function_declarations": declarations}]


def _usage_meta(usage: object) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    prompt = usage.get("promptTokenCount") or usage.get("prompt_token_count")
    candidates = usage.get("candidatesTokenCount") or usage.get("candidates_token_count")
    total = usage.get("totalTokenCount") or usage.get("total_token_count")
    thoughts = usage.get("thoughtsTokenCount") or usage.get("thoughts_token_count")
    meta: dict[str, Any] = {}
    if isinstance(prompt, int):
        meta["request_tokens"] = prompt
    if isinstance(candidates, int):
        meta["response_tokens"] = candidates
    if isinstance(total, int):
        meta["total_tokens"] = total
    elif isinstance(prompt, int) and isinstance(candidates, int):
        meta["total_tokens"] = prompt + candidates
    if isinstance(thoughts, int):
        meta["reasoning_tokens"] = thoughts
    return meta


def _maybe_warn_context_size(composed: ComposedPrompt, entry: CatalogEntry) -> None:
    estimated = estimate_tokens(composed.as_openai_messages())
    if estimated > int(entry.context_window * 0.9):
        _log.warning(
            "prompt near context limit model=%s estimated=%s window=%s",
            entry.model_id,
            estimated,
            entry.context_window,
        )
