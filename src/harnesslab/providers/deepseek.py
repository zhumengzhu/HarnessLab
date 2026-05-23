"""DeepSeek provider adapter (OpenAI-compatible chat completions API)."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import httpx

from harnesslab.core.models import Decision, Session

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT_SECONDS = 30.0

_SYSTEM_PROMPT = (
    "You are HarnessLab's model adapter. "
    "Prefer tool calls when tools are needed. "
    "When responding directly, be concise."
)


class DeepSeekModel:
    """ModelPort implementation backed by DeepSeek Chat Completions."""

    def __init__(
        self,
        *,
        tool_specs_provider: Callable[[], list[dict[str, Any]]],
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is required for DeepSeekModel. "
                "Set it in the environment or pass api_key explicitly."
            )
        self._tool_specs_provider = tool_specs_provider
        self._base_url = base_url or os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL
        self._model_name = model_name or os.getenv("DEEPSEEK_MODEL") or DEFAULT_MODEL
        self._client = httpx.Client(
            base_url=self._base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        self._last_call_meta: dict[str, Any] = {
            "provider": "deepseek",
            "model_name": self._model_name,
        }

    def decide(self, session: Session, user_input: str) -> Decision:
        body = self._request_body(session)
        try:
            response = self._client.post("/chat/completions", json=body)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            self._last_call_meta = {
                "provider": "deepseek",
                "model_name": self._model_name,
            }
            return Decision(
                kind="assistant",
                assistant_message=f"DeepSeek request failed: {type(exc).__name__}: {exc}",
            )

        self._last_call_meta = {
            "provider": "deepseek",
            "model_name": self._model_name,
            **_usage_meta(payload.get("usage")),
        }
        return _decision_from_payload(payload)

    def last_call_meta(self) -> dict[str, Any]:
        return dict(self._last_call_meta)

    def _request_body(self, session: Session) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model_name,
            "messages": _to_openai_messages(session),
            "temperature": 0,
        }
        tools = self._tool_specs_provider()
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body


def _decision_from_payload(payload: dict[str, Any]) -> Decision:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return Decision(
            kind="assistant",
            assistant_message="DeepSeek response invalid: missing choices.",
        )
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message", {})
    if not isinstance(message, dict):
        return Decision(
            kind="assistant",
            assistant_message="DeepSeek response invalid: malformed message.",
        )

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        function = tool_calls[0].get("function", {}) if isinstance(tool_calls[0], dict) else {}
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not name:
            return Decision(
                kind="assistant",
                assistant_message="DeepSeek tool call invalid: missing function name.",
            )
        if not isinstance(arguments, str):
            return Decision(
                kind="assistant",
                assistant_message="DeepSeek tool call invalid: arguments must be a JSON string.",
            )
        try:
            tool_args = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return Decision(
                kind="assistant",
                assistant_message=f"DeepSeek tool call invalid JSON args: {exc.msg}",
            )
        if not isinstance(tool_args, dict):
            return Decision(
                kind="assistant",
                assistant_message="DeepSeek tool call invalid: JSON args must be an object.",
            )
        return Decision(kind="tool", tool_name=name, tool_args=tool_args)

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return Decision(kind="assistant", assistant_message=content.strip())
    return Decision(
        kind="assistant",
        assistant_message="DeepSeek returned an empty response.",
    )


def _to_openai_messages(session: Session) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for msg in session.messages:
        messages.append({"role": msg.role, "content": msg.content})
    return messages


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
