"""Google Gemini generateContent transport (SDK-backed, Post-MVP P5)."""

from __future__ import annotations

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

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

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


def is_context_overflow_error(exc: genai_errors.APIError) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in _OVERFLOW_HINTS)


def overflow_message_from_error(exc: genai_errors.APIError) -> str:
    return f"Gemini context length exceeded: {exc}"
