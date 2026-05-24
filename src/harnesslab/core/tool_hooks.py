"""Tool lifecycle hooks (pre/post execution)."""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Literal
from urllib import request

from harnesslab.core.models import ToolCall, ToolResult

HookPhase = Literal["pre_tool", "post_tool"]
HookType = Literal["prompt", "shell", "http"]
HookAction = Literal["allow", "warn", "block"]


@dataclass(frozen=True)
class HookSpec:
    name: str
    hook_type: HookType
    config: dict[str, Any]


@dataclass(frozen=True)
class HookDecision:
    action: HookAction = "allow"
    reason: str | None = None


@dataclass
class ToolHookRunner:
    pre_hooks: list[HookSpec]
    post_hooks: list[HookSpec]

    def run_pre(self, hook: HookSpec, call: ToolCall) -> HookDecision:
        payload = {
            "session_id": call.session_id,
            "tool_name": call.name,
            "tool_args": call.args,
        }
        return _run_one_hook(hook, payload)

    def run_post(self, hook: HookSpec, call: ToolCall, result: ToolResult) -> HookDecision:
        payload = {
            "session_id": call.session_id,
            "tool_name": call.name,
            "tool_args": call.args,
            "tool_result": {
                "ok": result.ok,
                "error": result.error,
                "output_size": len(result.output),
            },
        }
        return _run_one_hook(hook, payload)


def build_hook_runner(
    pre_tool: tuple[dict[str, Any], ...],
    post_tool: tuple[dict[str, Any], ...],
) -> ToolHookRunner:
    return ToolHookRunner(
        pre_hooks=[_hook_spec(i, raw) for i, raw in enumerate(pre_tool)],
        post_hooks=[_hook_spec(i, raw) for i, raw in enumerate(post_tool)],
    )


def _hook_spec(index: int, raw: dict[str, Any]) -> HookSpec:
    hook_type = str(raw.get("type", "prompt")).strip().lower()
    if hook_type not in {"prompt", "shell", "http"}:
        hook_type = "prompt"
    name = str(raw.get("name", f"hook_{index}")).strip() or f"hook_{index}"
    config = raw.get("config", {})
    if not isinstance(config, dict):
        config = {}
    return HookSpec(name=name, hook_type=hook_type, config=config)  # type: ignore[arg-type]


def _run_one_hook(hook: HookSpec, payload: dict[str, Any]) -> HookDecision:
    if hook.hook_type == "prompt":
        return _run_prompt_hook(hook, payload)
    if hook.hook_type == "shell":
        return _run_shell_hook(hook, payload)
    return _run_http_hook(hook, payload)


def _run_prompt_hook(hook: HookSpec, payload: dict[str, Any]) -> HookDecision:
    tool_name = str(payload.get("tool_name", ""))
    contains = str(hook.config.get("tool_name_contains", "")).strip()
    if contains and contains not in tool_name:
        return HookDecision()
    action = str(hook.config.get("action", "allow")).strip().lower()
    if action not in {"allow", "warn", "block"}:
        action = "allow"
    reason = str(hook.config.get("reason", "")).strip() or None
    return HookDecision(action=action, reason=reason)  # type: ignore[arg-type]


def _run_shell_hook(hook: HookSpec, payload: dict[str, Any]) -> HookDecision:
    command = str(hook.config.get("command", "")).strip()
    if not command:
        return HookDecision()
    timeout_ms = int(hook.config.get("timeout_ms", 3000))
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=max(1, timeout_ms) / 1000.0,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"shell hook exited {proc.returncode}: {proc.stderr.strip()}")
    return _decision_from_text(proc.stdout)


def _run_http_hook(hook: HookSpec, payload: dict[str, Any]) -> HookDecision:
    url = str(hook.config.get("url", "")).strip()
    if not url:
        return HookDecision()
    timeout_ms = int(hook.config.get("timeout_ms", 3000))
    req = request.Request(  # noqa: S310
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=max(1, timeout_ms) / 1000.0) as resp:  # noqa: S310
        text = resp.read().decode("utf-8")
    return _decision_from_text(text)


def _decision_from_text(text: str) -> HookDecision:
    raw = text.strip()
    if not raw:
        return HookDecision()
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return HookDecision()
    action = str(parsed.get("action", "allow")).strip().lower()
    if action not in {"allow", "warn", "block"}:
        action = "allow"
    reason = parsed.get("reason")
    reason_text = str(reason).strip() if reason is not None else None
    return HookDecision(action=action, reason=reason_text or None)  # type: ignore[arg-type]
