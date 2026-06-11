"""Google Gemini generateContent transport (SDK-backed, Post-MVP P5)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from google import genai
from google.genai import errors as genai_errors

from harnesslab.core.compaction import ModelOverflowError

_OVERFLOW_HINTS = (
    "context_length_exceeded",
    "context length exceeded",
    "maximum context length",
    "too many tokens",
    "prompt is too long",
    "input token count",
)


class _GenaiModels(Protocol):
    def generate_content(
        self,
        *,
        model: str,
        contents: Any,
        config: Any | None = None,
    ) -> Any: ...

    def generate_content_stream(
        self,
        *,
        model: str,
        contents: Any,
        config: Any | None = None,
    ) -> Any: ...


class GoogleGenAITransport:
    """Thin wrapper around ``google.genai`` generateContent."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 30.0,
        client: genai.Client | None = None,
    ) -> None:
        if client is not None:
            self._models: _GenaiModels = client.models
            return
        http_options = genai.types.HttpOptions(timeout=int(timeout_seconds * 1000))
        self._models = genai.Client(api_key=api_key, http_options=http_options).models

    def generate_content(self, body: dict[str, Any]) -> dict[str, Any]:
        """Execute one generateContent call; return a JSON-like response dict."""

        config = _build_generate_config(body)
        try:
            response = self._models.generate_content(
                model=body["model"],
                contents=body["contents"],
                config=config,
            )
        except genai_errors.ClientError as exc:
            if is_context_overflow_error(exc):
                raise ModelOverflowError(overflow_message_from_error(exc)) from exc
            raise
        except genai_errors.ServerError as exc:
            if is_context_overflow_error(exc):
                raise ModelOverflowError(overflow_message_from_error(exc)) from exc
            raise

        return response.model_dump(mode="json")

    def generate_content_stream(
        self,
        body: dict[str, Any],
        *,
        on_delta: Callable[[str, str], None],
    ) -> dict[str, Any]:
        """Stream generateContent; invoke ``on_delta(kind, text)`` per chunk."""

        config = _build_generate_config(body)
        last_payload: dict[str, Any] | None = None
        try:
            for chunk in self._models.generate_content_stream(
                model=body["model"],
                contents=body["contents"],
                config=config,
            ):
                dumped = chunk.model_dump(mode="json")
                last_payload = dumped
                for part in _iter_text_parts(dumped):
                    kind = "reasoning" if part.get("thought") else "assistant"
                    text = str(part.get("text") or "")
                    if text:
                        on_delta(kind, text)
        except genai_errors.ClientError as exc:
            if is_context_overflow_error(exc):
                raise ModelOverflowError(overflow_message_from_error(exc)) from exc
            raise
        except genai_errors.ServerError as exc:
            if is_context_overflow_error(exc):
                raise ModelOverflowError(overflow_message_from_error(exc)) from exc
            raise

        if last_payload is None:
            return {"candidates": []}
        return last_payload


def _build_generate_config(body: dict[str, Any]) -> Any | None:
    from google.genai import types

    config_kwargs: dict[str, Any] = {}
    thinking_config = body.get("thinking_config")
    if isinstance(thinking_config, dict) and thinking_config:
        config_kwargs["thinking_config"] = types.ThinkingConfig(**thinking_config)
    tools = body.get("tools")
    if tools:
        config_kwargs["tools"] = tools
        config_kwargs["tool_config"] = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="AUTO")
        )
    system_instruction = body.get("system_instruction")
    if isinstance(system_instruction, dict):
        config_kwargs["system_instruction"] = system_instruction
    return types.GenerateContentConfig(**config_kwargs) if config_kwargs else None


def _iter_text_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return parts
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        raw_parts = content.get("parts")
        if not isinstance(raw_parts, list):
            continue
        for part in raw_parts:
            if isinstance(part, dict):
                parts.append(part)
    return parts


def is_context_overflow_error(exc: genai_errors.APIError) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in _OVERFLOW_HINTS)


def overflow_message_from_error(exc: genai_errors.APIError) -> str:
    return f"Gemini context length exceeded: {exc}"
