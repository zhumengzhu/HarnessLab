"""DeepSeek provider adapter (OpenAI-compatible chat completions API)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import httpx

from harnesslab.core.compaction import ModelOverflowError, estimate_tokens
from harnesslab.core.models import Decision, Session
from harnesslab.core.prompt import ComposedPrompt, PromptBlock, PromptComposer
from harnesslab.providers.model_resolve import (
    DEFAULT_DEEPSEEK_MODEL,
    resolve_deepseek_model_name,
)

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
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
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
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
        self._client = httpx.Client(
            base_url=self._base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        self._composer = composer or PromptComposer()
        self._dynamic_blocks_provider = dynamic_blocks_provider or _no_dynamic_blocks
        self._last_call_meta: dict[str, Any] = {
            "provider": "deepseek",
            "model_name": self._model_name,
        }
        self._last_prompt: ComposedPrompt | None = None

    def decide(self, session: Session, user_input: str) -> Decision:
        body = self._request_body(session)
        prompt_meta = _prompt_meta(self._last_prompt)
        base_meta = {
            "provider": "deepseek",
            "model_name": self._model_name,
            **prompt_meta,
        }
        try:
            response = self._client.post("/chat/completions", json=body)
            if _is_context_overflow(response):
                self._last_call_meta = dict(base_meta)
                raise ModelOverflowError(_overflow_message(response))
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            self._last_call_meta = dict(base_meta)
            return Decision(
                kind="final",
                assistant_message=f"DeepSeek request failed: {type(exc).__name__}: {exc}",
            )

        self._last_call_meta = {
            **base_meta,
            **_usage_meta(payload.get("usage")),
        }
        return _decision_from_payload(payload)

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
        body: dict[str, Any] = {
            "model": self._model_name,
            "messages": composed.as_openai_messages(),
            "temperature": 0,
        }
        if self._thinking_mode in {"enabled", "disabled"}:
            body["thinking"] = {"type": self._thinking_mode}
        tools = self._tool_specs_provider()
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body


def _decision_from_payload(payload: dict[str, Any]) -> Decision:
    """Translate one DeepSeek response into a ``Decision``.

    Tool calls produce ``kind="tool"`` (non-terminal — the inner loop
    will execute the tool and call the model again). Plain assistant
    text with no tool calls produces ``kind="final"``: that is the
    OpenAI function-calling convention for "the model considers itself
    done".
    """

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return Decision(
            kind="final",
            assistant_message="DeepSeek response invalid: missing choices.",
        )
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message", {})
    if not isinstance(message, dict):
        return Decision(
            kind="final",
            assistant_message="DeepSeek response invalid: malformed message.",
        )

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        function = tool_calls[0].get("function", {}) if isinstance(tool_calls[0], dict) else {}
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not name:
            return Decision(
                kind="final",
                assistant_message="DeepSeek tool call invalid: missing function name.",
            )
        if not isinstance(arguments, str):
            return Decision(
                kind="final",
                assistant_message="DeepSeek tool call invalid: arguments must be a JSON string.",
            )
        try:
            tool_args = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return Decision(
                kind="final",
                assistant_message=f"DeepSeek tool call invalid JSON args: {exc.msg}",
            )
        if not isinstance(tool_args, dict):
            return Decision(
                kind="final",
                assistant_message="DeepSeek tool call invalid: JSON args must be an object.",
            )
        return Decision(kind="tool", tool_name=name, tool_args=tool_args)

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return Decision(kind="final", assistant_message=content.strip())
    return Decision(
        kind="final",
        assistant_message="DeepSeek returned an empty response.",
    )


_OVERFLOW_HINTS = (
    "context_length_exceeded",
    "context length exceeded",
    "maximum context length",
    "too many tokens",
)


def _is_context_overflow(response: httpx.Response) -> bool:
    """Detect OpenAI / DeepSeek context-overflow responses.

    These come back as HTTP 400 with an ``error.code`` of
    ``context_length_exceeded`` (or a similar phrase in
    ``error.message``). We treat any 400 whose body mentions one of
    the hint strings as an overflow so the loop can run emergency
    compaction instead of bubbling the error to the user.
    """

    if response.status_code != 400:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return False
    code = (error.get("code") or "").lower()
    msg = (error.get("message") or "").lower()
    return any(hint in code or hint in msg for hint in _OVERFLOW_HINTS)


def _overflow_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return "DeepSeek context length exceeded"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return f"DeepSeek context length exceeded: {error['message']}"
    return "DeepSeek context length exceeded"


def _prompt_meta(prompt: ComposedPrompt | None) -> dict[str, Any]:
    """Summarize a composed prompt for the ``model_call.context`` snapshot.

    Static blocks live above the conversation; dynamic blocks
    (env / agents_md / tool_guide / etc.) are the runtime layer
    contributed per-call; everything else (the rendered messages
    themselves) is accounted for separately by the loop via
    ``estimate_messages_tokens``.
    """

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
