"""Run a TaskSuite against the production loop and produce TaskResults.

Each task runs in its own temporary workspace with a fresh ``FrozenClock``
and ``SeqIdProvider`` so that span ids, timestamps, and duration_ms are
fully deterministic across machines.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from harnesslab.core.budget import BudgetLimits
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import SpanRecord
from harnesslab.core.replay import ReplayModel, ReplaySpanRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.core.simple_model import SimpleModel
from harnesslab.eval.task import (
    ExpectedEvent,
    ExpectedSpan,
    Task,
    TaskMetrics,
    TaskResult,
    TaskSuite,
)
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.telemetry.span_attributes import (
    HARNESSLAB_COMPACTION_KEEP_LAST,
    HARNESSLAB_COMPACTION_MESSAGES_AFTER,
    HARNESSLAB_COMPACTION_THRESHOLD_TOKENS,
    HARNESSLAB_COMPACTION_TRIGGER,
    HARNESSLAB_STEPS_USED,
    HARNESSLAB_TERMINAL_REASON,
    HARNESSLAB_TOOL_OK,
)
from harnesslab.tools.fetch_url_tool import FetchUrlTool
from harnesslab.tools.file_tools import (
    EditFileTool,
    GlobTool,
    GrepTool,
    ReadFileTool,
    WriteFileTool,
)
from harnesslab.tools.patch import ApplyPatchTool
from harnesslab.tools.registry import ToolRegistry
from harnesslab.tools.research_tools import HtmlToMarkdownTool, WebSearchTool
from harnesslab.tools.shell_tool import RunShellSafeTool
from harnesslab.tools.spawn_sub_agent import SpawnSubAgentTool


def _limits_for_task(task: Task, base: RuntimeLimits | None = None) -> RuntimeLimits:
    base = base or RuntimeLimits()
    if task.limits is None:
        return base
    return replace(base, **task.limits.model_dump(exclude_none=True))


def _eval_web_search_transport() -> httpx.MockTransport:
    """Deterministic DuckDuckGo HTML for replay eval tasks."""

    html = """
    <html><body>
      <a class="result__a" href="https://example.com/harnesslab">HarnessLab</a>
      <a class="result__snippet" href="https://example.com/harnesslab">
        Learning-first agent harness.
      </a>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "duckduckgo.com" and request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(200, text=html)

    return httpx.MockTransport(handler)


def _build_tool_registry(workspace: Path, limits: RuntimeLimits) -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(ReadFileTool(workspace, limits=limits))
    tools.register(WriteFileTool(workspace, limits=limits))
    tools.register(EditFileTool(workspace, limits=limits))
    tools.register(ApplyPatchTool(workspace, limits=limits))
    tools.register(GrepTool(workspace, limits=limits))
    tools.register(GlobTool(workspace, limits=limits))
    tools.register(FetchUrlTool(limits=limits))
    tools.register(WebSearchTool(backend="duckduckgo", transport=_eval_web_search_transport()))
    tools.register(HtmlToMarkdownTool(limits=limits))
    tools.register(RunShellSafeTool(workspace, limits=limits))
    return tools


def _payload_contains(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Recursive subset match: every (k, v) in expected must equal in actual."""

    for k, v in expected.items():
        if k not in actual:
            return False
        if isinstance(v, dict) and isinstance(actual[k], dict):
            if not _payload_contains(actual[k], v):
                return False
        elif actual[k] != v:
            return False
    return True


def _expected_spans_for_task(task: Task) -> list[ExpectedSpan]:
    explicit = list(task.expected.spans_include)
    if explicit:
        return explicit
    return [_legacy_event_to_span(ev) for ev in task.expected.events_include]


def _legacy_event_to_span(event: ExpectedEvent) -> ExpectedSpan:
    payload = event.payload_contains or {}
    et = event.event_type

    if et == "session_started":
        return ExpectedSpan(name="harnesslab.turn", span_event="session.created")

    if et == "user_input_received":
        turn_index = payload.get("turn_index")
        return ExpectedSpan(
            name="harnesslab.turn",
            turn_index=int(turn_index) if turn_index is not None else None,
        )

    if et == "tool_executed":
        tool = str(payload.get("tool", ""))
        span_name = f"tool.{tool}" if tool else "tool.*"
        attrs: dict[str, Any] = {HARNESSLAB_TOOL_OK: payload.get("ok", True)}
        for key, value in payload.items():
            if key == "tool":
                continue
            if key == "ok":
                attrs[HARNESSLAB_TOOL_OK] = value
            else:
                attrs[key] = value
        return ExpectedSpan(name=span_name, attributes_contains=attrs)

    if et == "tool_denied":
        tool = str(payload.get("tool", ""))
        event_attrs = {k: v for k, v in payload.items() if k != "tool"}
        return ExpectedSpan(
            name=f"tool.{tool}",
            span_event="tool.policy_denied",
            on_span=f"tool.{tool}",
            attributes_contains=event_attrs or None,
        )

    if et == "tool_invalid_args":
        tool = str(payload.get("tool", ""))
        return ExpectedSpan(
            name=f"tool.{tool}",
            span_event="tool.args_invalid",
            on_span=f"tool.{tool}",
        )

    if et == "session_finished":
        attrs: dict[str, Any] = {}
        if "reason" in payload:
            attrs[HARNESSLAB_TERMINAL_REASON] = payload["reason"]
        if "steps" in payload:
            attrs[HARNESSLAB_STEPS_USED] = payload["steps"]
        return ExpectedSpan(name="harnesslab.turn", attributes_contains=attrs or None)

    if et == "decision_made":
        return ExpectedSpan(
            name="harnesslab.step",
            span_event="decision.applied",
            attributes_contains=dict(payload) or None,
        )

    if et == "plan_emitted":
        return ExpectedSpan(
            name="*",
            span_event="plan.emitted",
            attributes_contains=dict(payload) or None,
        )

    if et in {"memory_written", "workspace_memory_written"}:
        attrs = dict(payload)
        return ExpectedSpan(
            name="*",
            span_event="memory.written",
            attributes_contains=attrs or None,
        )

    if et in {"memory_read", "workspace_memory_read"}:
        attrs = dict(payload)
        if et == "workspace_memory_read":
            attrs.setdefault("scope", "workspace")
        return ExpectedSpan(
            name="*",
            span_event="memory.read",
            attributes_contains=attrs or None,
        )

    if et == "compaction_started":
        return ExpectedSpan(
            name="context.compact",
            attributes_contains=_map_compaction_payload(payload),
        )

    if et == "compaction_completed":
        return ExpectedSpan(
            name="context.compact",
            attributes_contains=_map_compaction_payload(payload),
            attribute_keys_present=[HARNESSLAB_COMPACTION_MESSAGES_AFTER],
        )

    if et == "budget_hard_exceeded":
        return ExpectedSpan(
            name="*",
            span_event="budget.hard_exceeded",
            attributes_contains=dict(payload) or None,
        )

    if et == "budget_soft_threshold":
        return ExpectedSpan(
            name="*",
            span_event="budget.soft_threshold",
            attributes_contains=dict(payload) or None,
        )

    return ExpectedSpan(name=et, attributes_contains=payload or None)


def _map_compaction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    if "trigger" in payload:
        mapped[HARNESSLAB_COMPACTION_TRIGGER] = payload["trigger"]
    if "keep_last" in payload:
        mapped[HARNESSLAB_COMPACTION_KEEP_LAST] = payload["keep_last"]
    if "threshold_tokens" in payload:
        mapped[HARNESSLAB_COMPACTION_THRESHOLD_TOKENS] = payload["threshold_tokens"]
    if "estimated_tokens" in payload:
        mapped["estimated_tokens_before"] = payload["estimated_tokens"]
    for key, value in payload.items():
        if key not in {
            "trigger",
            "keep_last",
            "threshold_tokens",
            "estimated_tokens",
        }:
            mapped[key] = value
    return mapped


def _forbidden_span_checks(task: Task) -> list[str]:
    forbidden = list(task.expected.no_span_names)
    for et in task.expected.no_event_types:
        if et == "tool_executed":
            forbidden.append("tool.")
        elif et == "tool_denied":
            forbidden.append("tool.policy_denied")
        elif et == "tool_invalid_args":
            forbidden.append("tool.args_invalid")
        else:
            forbidden.append(et)
    return forbidden


def _evaluate(task: Task, spans: list[SpanRecord], final_reply: str) -> TaskResult:
    failures: list[str] = []
    ordered = _chronological_spans(spans)

    for needle in task.expected.final_reply_contains:
        if needle not in final_reply:
            failures.append(f"final reply missing substring: {needle!r}")

    cursor = 0
    for expected in _expected_spans_for_task(task):
        search_start = 0 if _search_from_beginning(expected) else cursor
        matched_at = _find_span(ordered, expected, start=search_start)
        if matched_at == -1 and search_start == 0 and cursor > 0:
            matched_at = _find_span(ordered, expected, start=cursor)
        if matched_at == -1:
            failures.append(_format_missing_span(expected))
        else:
            cursor = max(cursor, matched_at + 1)

    for forbidden in _forbidden_span_checks(task):
        if forbidden.endswith("."):
            if any(s.name.startswith(forbidden) and s.name != "tool.hooks.pre" for s in ordered):
                if forbidden == "tool." and not _has_tool_execution(ordered):
                    continue
                if forbidden == "tool.":
                    failures.append("forbidden span appeared: tool execution")
        elif any(
            any(ev.name == forbidden for ev in s.events) for s in ordered
        ):
            failures.append(f"forbidden span event appeared: {forbidden}")
        elif any(s.name == forbidden for s in ordered):
            failures.append(f"forbidden span name appeared: {forbidden}")

    metrics = TaskMetrics(
        turns=len(task.turns),
        tool_calls=sum(
            1
            for s in ordered
            if s.name.startswith("tool.")
            and not s.name.startswith("tool.hooks.")
            and s.name.count(".") == 1
        ),
        tool_failures=sum(
            1
            for s in ordered
            if s.name.startswith("tool.")
            and s.attributes.get(HARNESSLAB_TOOL_OK) is False
            and not any(
                ev.name in {"tool.policy_denied", "tool.args_invalid"} for ev in s.events
            )
        ),
        denials=sum(
            1
            for s in ordered
            if any(ev.name == "tool.policy_denied" for ev in s.events)
        ),
        invalid_args=sum(
            1
            for s in ordered
            if any(ev.name == "tool.args_invalid" for ev in s.events)
        ),
    )

    return TaskResult(
        task_name=task.name,
        passed=not failures,
        failures=failures,
        metrics=metrics,
        final_reply=final_reply,
    )


def _chronological_spans(spans: list[SpanRecord]) -> list[SpanRecord]:
    return sorted(spans, key=lambda s: (s.start_time, s.span_id))


def _has_tool_execution(spans: list[SpanRecord]) -> bool:
    return any(
        s.name.startswith("tool.")
        and not s.name.startswith("tool.hooks.")
        and s.name.count(".") == 1
        and s.attributes.get(HARNESSLAB_TOOL_OK) is True
        for s in spans
    )


def _search_from_beginning(expected: ExpectedSpan) -> bool:
    if expected.attribute_keys_present:
        return True
    if expected.name == "harnesslab.turn" and expected.attributes_contains:
        return HARNESSLAB_TERMINAL_REASON in expected.attributes_contains
    return False


def _find_span(spans: list[SpanRecord], expected: ExpectedSpan, start: int) -> int:
    for i in range(start, len(spans)):
        span = spans[i]
        if expected.name != "*":
            if expected.name.endswith(".*"):
                if not span.name.startswith(expected.name[:-2]):
                    continue
            elif span.name != expected.name:
                continue
        if expected.turn_index is not None and span.turn_index != expected.turn_index:
            continue
        if expected.attribute_keys_present is not None:
            if not all(key in span.attributes for key in expected.attribute_keys_present):
                continue
        if expected.span_event is not None:
            if expected.name == "*":
                if not _span_has_event(span, expected):
                    continue
            else:
                target_name = expected.on_span or expected.name
                if span.name != target_name:
                    continue
                if not _span_has_event(span, expected):
                    continue
        elif expected.attributes_contains is not None and not _payload_contains(
            span.attributes, expected.attributes_contains
        ):
            continue
        return i
    return -1


def _span_has_event(span: SpanRecord, expected: ExpectedSpan) -> bool:
    assert expected.span_event is not None
    for event in span.events:
        if event.name != expected.span_event:
            continue
        if expected.attributes_contains is None:
            return True
        if _payload_contains(event.attributes, expected.attributes_contains):
            return True
    return False


def _format_missing_span(expected: ExpectedSpan) -> str:
    if expected.span_event:
        return (
            f"expected span not found in order: {expected.name} "
            f"with event {expected.span_event!r}"
        )
    if expected.attributes_contains:
        return (
            f"expected span not found in order: {expected.name} "
            f"with attributes containing {expected.attributes_contains}"
        )
    return f"expected span not found in order: {expected.name}"


class TaskRunner:
    """Drive HarnessLoop end-to-end for each task, in isolation.

    ``base_limits`` / ``shell_profile`` let an offline config search (the
    Bayesian tuner, ``docs/research/bayesian-self-evolution.md`` Layer B1)
    score a candidate runtime configuration against the suite. Per-task
    ``limits`` / ``policy`` overrides still win so each task preserves the
    behaviour it was written to exercise.
    """

    def __init__(
        self,
        clock_start: datetime | None = None,
        *,
        base_limits: RuntimeLimits | None = None,
        shell_profile: str | None = None,
    ) -> None:
        self._clock_start = clock_start or DEFAULT_REPLAY_CLOCK_START
        self._base_limits = base_limits or RuntimeLimits()
        self._shell_profile = shell_profile

    def run(self, suite: TaskSuite) -> list[TaskResult]:
        return [self.run_one(t) for t in suite.tasks]

    def run_one(self, task: Task) -> TaskResult:
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            spans, final_reply = self._drive_loop(task, workspace)
            return _evaluate(task, spans, final_reply)

    def _drive_loop(
        self, task: Task, workspace: Path
    ) -> tuple[list[SpanRecord], str]:
        limits = _limits_for_task(task, self._base_limits)
        tools = _build_tool_registry(workspace, limits)
        memory = InMemoryMemoryStore()

        recorder = ReplaySpanRecorder()
        replay_meta = dict(task.replay_call_meta or {})
        model: Any = (
            ReplayModel(decisions=task.decisions, call_meta=replay_meta)
            if task.decisions
            else SimpleModel()
        )

        budget_limits = BudgetLimits(enabled=False)
        if task.budget is not None:
            budget_limits = BudgetLimits(
                enabled=task.budget.enabled,
                soft_ratio=task.budget.soft_ratio,
                max_session_cost_usd_total=task.budget.max_session_cost_usd_total,
                action_on_hard=task.budget.action_on_hard,  # type: ignore[arg-type]
            )

        loop_holder: list[HarnessLoop] = []
        tools.register(SpawnSubAgentTool(lambda: loop_holder[0]))
        loop = HarnessLoop(
            model=model,
            policy=DefaultPolicy(
                workspace_root=workspace,
                shell_profile=(
                    task.policy.shell_profile
                    if task.policy is not None and task.policy.shell_profile is not None
                    else self._shell_profile
                ),
                enable_spawn_sub_agent=True,
            ),
            sessions=InMemorySessionStore(),
            tools=tools,
            spans=recorder,
            clock=FrozenClock(start=self._clock_start),
            ids=SeqIdProvider(),
            limits=limits,
            memory=memory,
            workspace_root=workspace,
            budget_limits=budget_limits,
        )
        loop_holder.append(loop)

        session = loop.start(goal=task.goal)
        replies = _drive_turns(loop, session.id, task.turns, default_goal=task.goal)
        final_reply = replies[-1] if replies else ""
        return recorder.spans, final_reply


def _drive_turns(
    loop: HarnessLoop,
    session_id: str,
    turns: Iterable[Any],
    *,
    default_goal: str,
) -> list[str]:
    replies: list[str] = []
    current_id = session_id
    for turn in turns:
        if turn.new_session:
            session = loop.start(goal=turn.goal or default_goal)
            current_id = session.id
        replies.append(
            loop.run_session(current_id, turn.input, max_steps=turn.max_steps)
        )
    return replies
