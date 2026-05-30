from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from harnesslab.checkpoint.store import MUTATING_TOOLS, collect_file_snapshots
from harnesslab.core.artifact_policy import maybe_externalize_tool_output
from harnesslab.core.budget import (
    BudgetBreach,
    BudgetLimits,
    TurnBudgetUsage,
    detect_budget_breaches,
)
from harnesslab.core.compaction import (
    ModelOverflowError,
    Summarizer,
    compact_messages,
    estimate_messages_tokens,
    parse_compact_command,
    should_compact,
)
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.context import (
    make_conversation_snapshot,
    merge_adapter_breakdown,
)
from harnesslab.core.contracts import (
    ArtifactStorePort,
    ClockPort,
    IdPort,
    MemoryStorePort,
    ModelPort,
    PolicyPort,
    SemanticMemoryStorePort,
    SessionStorePort,
    TraceRecorderPort,
)
from harnesslab.core.memory_policy import (
    append_note,
    format_memory_message,
    format_remember_global_note,
    format_remember_note,
    format_workspace_memory_message,
    parse_remember_command,
    parse_remember_global_command,
    session_memory_key,
    workspace_memory_key,
)
from harnesslab.core.models import (
    TERMINAL_DECISION_KINDS,
    Decision,
    Message,
    Session,
    ToolCall,
    ToolResult,
    TraceEvent,
)
from harnesslab.core.runtime import SystemClock, UuidIdProvider
from harnesslab.core.skill_policy import (
    SkillCommand,
    format_skill_state_message,
    list_skills,
    parse_direct_skill_command,
    parse_skill_command,
    selected_skills_from_messages,
)
from harnesslab.core.stream_context import (
    bind_stream_sink,
    reset_stream_sink,
    set_stream_step_index,
)
from harnesslab.core.title import TitleNamer, derive_title_from_text
from harnesslab.core.tool_hooks import ToolHookRunner
from harnesslab.providers.pricing import estimate_call_cost_usd
from harnesslab.telemetry.log import get_logger
from harnesslab.tools.registry import ToolRegistry

_TRACE_OUTPUT_PREVIEW_BYTES = 512
_log = get_logger("core.loop")

DEFAULT_MAX_STEPS = 20
SKILL_INVOKE_MIN_STEPS = 40


class HarnessLoop:
    """Orchestrate one session's interaction with the model and tools.

    The public surface is two methods:

    - :meth:`run_turn` runs a single decision step (backwards-compatible
      with the original one-step loop; equivalent to
      ``run_session(..., max_steps=1)``).
    - :meth:`run_session` runs the autonomous inner loop: it keeps calling
      the model — feeding tool results back in via ``session.messages`` —
      until the model returns a terminal decision (``final`` or
      ``ask_user``) or ``max_steps`` is exhausted.
    """

    def __init__(
        self,
        model: ModelPort,
        policy: PolicyPort,
        sessions: SessionStorePort,
        tools: ToolRegistry,
        trace: TraceRecorderPort,
        clock: ClockPort | None = None,
        ids: IdPort | None = None,
        limits: RuntimeLimits | None = None,
        summarizer: Summarizer | None = None,
        title_namer: TitleNamer | None = None,
        memory: MemoryStorePort | None = None,
        artifacts: ArtifactStorePort | None = None,
        checkpoint_store: Any | None = None,
        semantic_memory: SemanticMemoryStorePort | None = None,
        workspace_root: Path | None = None,
        replan_after_steps: int | None = None,
        budget_limits: BudgetLimits | None = None,
        hook_runner: ToolHookRunner | None = None,
        stream_sink: Any | None = None,
        turn_steer: Any | None = None,
    ) -> None:
        self._model = model
        self._policy = policy
        self._sessions = sessions
        self._tools = tools
        self._trace = trace
        self._clock: ClockPort = clock or SystemClock()
        self._ids: IdPort = ids or UuidIdProvider()
        self._limits: RuntimeLimits = limits or RuntimeLimits()
        self._summarizer: Summarizer | None = summarizer
        self._title_namer: TitleNamer | None = title_namer
        self._memory: MemoryStorePort | None = memory
        self._artifacts: ArtifactStorePort | None = artifacts
        self._checkpoint_store = checkpoint_store
        self._semantic_memory = semantic_memory
        self._workspace_root = workspace_root.resolve() if workspace_root else None
        self._replan_after_steps = (
            replan_after_steps
            if isinstance(replan_after_steps, int) and replan_after_steps > 0
            else None
        )
        self._budget_limits = budget_limits or BudgetLimits(enabled=False)
        self._hook_runner = hook_runner
        self._stream_sink = stream_sink
        self._turn_steer = turn_steer
        self._last_stream_reasoning: str | None = None

    def start(self, goal: str) -> Session:
        session = Session(
            id=self._ids.new_id("ses"),
            goal=goal,
            created_at=self._clock.now(),
            title=derive_title_from_text(goal),
        )
        self._sessions.create(session)
        self._record(
            session=session,
            event_type="session_started",
            payload=self._session_started_payload(goal=goal),
        )
        _log.info("session started id=%s goal=%r", session.id, goal[:80])
        return session

    def start_child(self, goal: str, parent_session_id: str) -> Session:
        """Start a child session linked to ``parent_session_id`` (multi-agent PoC)."""

        session = Session(
            id=self._ids.new_id("ses"),
            goal=goal,
            created_at=self._clock.now(),
            title=derive_title_from_text(goal),
            parent_session_id=parent_session_id,
        )
        self._sessions.create(session)
        self._record(
            session=session,
            event_type="session_started",
            payload={
                **self._session_started_payload(goal=goal),
                "parent_session_id": parent_session_id,
            },
        )
        return session

    def fork(self, source_id: str, *, goal: str | None = None) -> Session:
        """Create a new session seeded from ``source_id``'s messages.

        The forked session keeps a pointer back to its source via
        ``parent_session_id`` so the ``session show --history`` view
        can walk the lineage. The conversation is copied by value so
        edits to the fork do not mutate the parent.
        """

        parent = self._sessions.get(source_id)
        forked_id = self._ids.new_id("ses")
        # Each ``messages.id`` is a globally unique PRIMARY KEY in the
        # SQLite store, so copied-by-value messages need fresh ids and
        # session_id pointers.
        copied_messages = [
            m.model_copy(
                update={
                    "id": self._ids.new_id("msg"),
                    "session_id": forked_id,
                }
            )
            for m in parent.messages
        ]
        forked = Session(
            id=forked_id,
            goal=goal or parent.goal,
            created_at=self._clock.now(),
            title=derive_title_from_text(goal or parent.goal),
            parent_session_id=parent.id,
            model_backend=parent.model_backend,
            model_id=parent.model_id,
            model_effort=parent.model_effort,
            messages=copied_messages,
        )
        self._sessions.create(forked)
        self._record(
            session=forked,
            event_type="session_started",
            payload={
                **self._session_started_payload(goal=forked.goal),
                "parent_session_id": parent.id,
            },
        )
        return forked

    def run_turn(self, session_id: str, user_input: str) -> str:
        """Run exactly one decision step.

        Equivalent to ``run_session(..., max_steps=1)``. Kept as the
        narrow surface used by eval tasks and tests that want
        deterministic, single-step trace shapes.
        """

        return self.run_session(session_id, user_input, max_steps=1)

    def run_session(
        self,
        session_id: str,
        user_input: str,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> str:
        """Drive the model/tool loop until terminal or ``max_steps``.

        The model is consulted once per step. After a non-terminal
        decision (``tool`` or ``assistant``), the loop appends the
        relevant message to ``session.messages`` and calls the model
        again so it can react to the new state. The empty string is
        passed as ``user_input`` to follow-up calls; real model adapters
        rely on ``session.messages`` for the new signal, and
        ``SimpleModel`` falls through to its canned final response.
        """

        if max_steps < 1:
            raise ValueError(f"max_steps must be >= 1, got {max_steps}")

        session = self._sessions.get(session_id)
        session.status = "running"
        self._record(
            session=session,
            event_type="user_input_received",
            payload={
                "turn_index": session.turn_count,
                "user_input": user_input,
            },
        )
        session.messages.append(
            self._make_message(role="user", content=user_input, session=session)
        )
        self._inject_workspace_memory(session)
        self._inject_session_memory(session)

        remember_body = parse_remember_command(user_input)
        if remember_body is not None:
            return self._run_remember_turn(session, remember_body)

        global_body = parse_remember_global_command(user_input)
        if global_body is not None:
            return self._run_remember_global_turn(session, global_body)

        if parse_compact_command(user_input):
            return self._run_compact_turn(session)

        skill_command = parse_skill_command(user_input)
        if skill_command is None:
            skill_command = parse_direct_skill_command(
                user_input, list_skills(self._workspace_root)
            )
        model_user_input = user_input
        if skill_command is not None:
            if skill_command.kind == "invoke":
                model_user_input = self._prepare_skill_invoke(session, skill_command)
            else:
                return self._run_skill_turn(session, skill_command)

        effective_max_steps = max_steps
        if skill_command is not None and skill_command.kind == "invoke":
            effective_max_steps = max(max_steps, SKILL_INVOKE_MIN_STEPS)

        last_response = ""
        terminal_reason = "max_steps"
        steps_used = 0
        prev_terminal: str | None = None
        turn_usage = TurnBudgetUsage()
        turn_started_at = self._clock.now()
        session_wall_base = session.budget_usage.wall_time_ms_total

        for step_index in range(effective_max_steps):
            self._record(
                session=session,
                event_type="step_started",
                payload={
                    "step_index": step_index,
                    "reason": (
                        "initial" if step_index == 0 else f"after_{prev_terminal}"
                    ),
                },
            )
            _log.debug(
                "step started session=%s index=%s reason=%s",
                session.id,
                step_index,
                "initial" if step_index == 0 else f"after_{prev_terminal}",
            )

            if step_index > 0:
                self._apply_pending_steer(session, step_index=step_index)

            self._maybe_compact(session, trigger="threshold")
            if self._enforce_budget(
                session=session,
                turn_usage=turn_usage,
                turn_started_at=turn_started_at,
                session_wall_base=session_wall_base,
            ):
                terminal_reason = self._budget_limits.action_on_hard
                if terminal_reason == "error":
                    terminal_reason = "final"
                last_response = self._budget_stop_message(session)
                session.messages.append(
                    self._make_message(
                        role="assistant",
                        content=last_response,
                        session=session,
                    )
                )
                break

            step_input = model_user_input if step_index == 0 else ""
            self._record(
                session=session,
                event_type="model_call_started",
                payload={
                    "step_index": step_index,
                    "thinking_likely": self._model_thinking_likely(),
                },
            )
            decision, decision_started, decision_ended = self._call_model_with_overflow(
                session, step_input, step_index=step_index
            )
            turn_usage.llm_calls += 1
            session.budget_usage.llm_calls_total += 1
            token_total = self._model_total_tokens()
            if token_total is not None:
                session.budget_usage.tokens_total += token_total
            self._accumulate_model_cost(session)
            self._record(
                session=session,
                event_type="model_call",
                payload=self._model_call_payload(
                    decision=decision,
                    started_at=decision_started,
                    ended_at=decision_ended,
                    session=session,
                ),
            )
            self._record(
                session=session,
                event_type="decision_made",
                payload={
                    "kind": decision.kind,
                    "tool_name": decision.tool_name,
                    "tool_args": decision.tool_args,
                    "assistant_message": decision.assistant_message,
                    "reasoning_text": self._model_reasoning_text(),
                },
            )

            step_response, step_outcome = self._apply_decision(session, decision)
            if step_outcome in {"tool_ok", "tool_error"}:
                turn_usage.tool_calls += 1
                session.budget_usage.tool_calls_total += 1
            _log.debug(
                "decision applied session=%s kind=%s outcome=%s",
                session.id,
                decision.kind,
                step_outcome,
            )
            last_response = step_response
            prev_terminal = step_outcome
            steps_used = step_index + 1
            session.step_count += 1
            session.last_step_at = self._clock.now()

            self._record(
                session=session,
                event_type="step_completed",
                payload={
                    "step_index": step_index,
                    "outcome": step_outcome,
                },
            )

            turn_usage.wall_time_ms = self._elapsed_ms(turn_started_at)
            session.budget_usage.wall_time_ms_total = self._session_wall_time_total(
                base_ms=session_wall_base,
                turn_elapsed_ms=turn_usage.wall_time_ms,
            )
            if self._enforce_budget(
                session=session,
                turn_usage=turn_usage,
                turn_started_at=turn_started_at,
                session_wall_base=session_wall_base,
            ):
                terminal_reason = self._budget_limits.action_on_hard
                if terminal_reason == "error":
                    terminal_reason = "final"
                last_response = self._budget_stop_message(session)
                session.messages.append(
                    self._make_message(
                        role="assistant",
                        content=last_response,
                        session=session,
                    )
                )
                break

            if decision.kind in TERMINAL_DECISION_KINDS:
                terminal_reason = decision.kind
                break
            self._maybe_emit_replan_reminder(
                session=session,
                steps_used=steps_used,
                max_steps=effective_max_steps,
            )

        if (
            terminal_reason == "max_steps"
            and steps_used >= effective_max_steps
            and effective_max_steps > 1
        ):
            last_response = (
                f"Step budget reached ({effective_max_steps} inner steps). "
                "This session is still open — send **continue** to keep researching, "
                "or **summarize what you have so far** for a partial report."
            )
            session.messages.append(
                self._make_message(
                    role="assistant",
                    content=last_response,
                    session=session,
                )
            )
            session.status = "waiting_user"

        turn_usage.wall_time_ms = self._elapsed_ms(turn_started_at)
        session.budget_usage.wall_time_ms_total = self._session_wall_time_total(
            base_ms=session_wall_base,
            turn_elapsed_ms=turn_usage.wall_time_ms,
        )

        self._record(
            session=session,
            event_type="session_finished",
            payload={
                "reason": terminal_reason,
                "steps": steps_used,
            },
        )
        _log.info(
            "session finished id=%s reason=%s steps=%s turn=%s",
            session.id,
            terminal_reason,
            steps_used,
            session.turn_count + 1,
        )

        session.turn_count += 1
        if terminal_reason == "final":
            session.status = "done"
        elif terminal_reason == "ask_user":
            session.status = "waiting_user"
        # Hitting max_steps leaves status as "running" — the next
        # run_session call can extend the session.
        self._maybe_auto_title(session)
        self._sessions.save(session)
        return last_response

    def _maybe_auto_title(self, session: Session) -> None:
        """Replace the placeholder title after the first user turn.

        Runs at most once (``turn_count == 1``). Failures are silent;
        the derived title from :func:`derive_title_from_text` remains.
        """

        if session.turn_count != 1 or self._title_namer is None:
            return
        previous = session.title
        try:
            proposed = self._title_namer(session)
        except Exception:
            return
        if not proposed or proposed == previous:
            return
        session.title = proposed
        self._record(
            session=session,
            event_type="session_titled",
            payload={
                "title": proposed,
                "previous_title": previous,
                "source": "llm",
            },
        )

    def _run_remember_turn(self, session: Session, body: str) -> str:
        """Handle ``/remember`` without calling the model."""

        if self._memory is None:
            reply = "Memory store is not configured."
        else:
            self._write_remember_note(session, body)
            reply = "Stored in session memory."

        session.messages.append(
            self._make_message(role="assistant", content=reply, session=session)
        )
        self._record(
            session=session,
            event_type="session_finished",
            payload={"reason": "remember", "steps": 0},
        )
        session.turn_count += 1
        session.status = "running"
        self._maybe_auto_title(session)
        self._sessions.save(session)
        return reply

    def _run_remember_global_turn(self, session: Session, body: str) -> str:
        """Handle ``/remember-global`` without calling the model."""

        if self._memory is None or self._workspace_root is None:
            reply = "Workspace memory is not configured."
        else:
            self._write_remember_global_note(session, body)
            reply = "Stored in workspace memory."

        session.messages.append(
            self._make_message(role="assistant", content=reply, session=session)
        )
        self._record(
            session=session,
            event_type="session_finished",
            payload={"reason": "remember_global", "steps": 0},
        )
        session.turn_count += 1
        session.status = "running"
        self._maybe_auto_title(session)
        self._sessions.save(session)
        return reply

    def _run_compact_turn(self, session: Session) -> str:
        """Handle ``/compact`` — operator-initiated context compaction."""

        if session.messages and session.messages[-1].role == "user":
            if parse_compact_command(session.messages[-1].content):
                session.messages.pop()

        keep_last = self._limits.compaction_keep_last_messages
        before_count = len(session.messages)
        before_tokens = estimate_messages_tokens(session.messages)

        if before_count <= keep_last:
            reply = (
                f"No compaction needed ({before_count} messages; "
                f"keep_last={keep_last}, ~{before_tokens} est. tokens)."
            )
        else:
            self._do_compact(session, trigger="manual", keep_last=keep_last)
            after_count = len(session.messages)
            after_tokens = estimate_messages_tokens(session.messages)
            reply = (
                "Compacted session context.\n"
                f"- Before: {before_count} messages (~{before_tokens} est. tokens)\n"
                f"- After: {after_count} messages (~{after_tokens} est. tokens)\n"
                f"- Kept last {keep_last} message(s); older turns replaced by summary.\n"
                "Note: raw thinking on compacted-away assistant turns is not sent to "
                "the model again; use /remember for durable facts."
            )

        session.messages.append(
            self._make_message(role="assistant", content=reply, session=session)
        )
        self._record(
            session=session,
            event_type="session_finished",
            payload={"reason": "compact", "steps": 0},
        )
        session.turn_count += 1
        session.status = "running"
        self._maybe_auto_title(session)
        self._sessions.save(session)
        return reply

    def _prepare_skill_invoke(self, session: Session, command: SkillCommand) -> str:
        """Pin ``command.name`` and return the task text for the model loop."""

        available = list_skills(self._workspace_root)
        name = (command.name or "").strip()
        task = (command.task or "").strip()
        if not name or name not in available:
            raise ValueError(f"Skill '{name}' not found under skills/*.md.")
        if not task:
            raise ValueError("skill invoke requires a task after the skill name")

        selected = selected_skills_from_messages(session.messages)
        if name not in selected:
            selected.append(name)
        session.messages.append(
            self._make_message(
                role="system",
                content=format_skill_state_message(selected),
                session=session,
            )
        )
        self._sessions.save(session)
        return task

    def _run_skill_turn(self, session: Session, command: SkillCommand) -> str:
        """Handle ``/skill`` commands without model calls."""

        available = list_skills(self._workspace_root)
        selected = selected_skills_from_messages(session.messages)

        if command.kind == "list":
            lines = [
                "Skills available:",
                *(f"- {name}" for name in available),
            ]
            if not available:
                lines.append("- (none)")
            lines.append("")
            lines.append(
                "Selected skills: " + (", ".join(selected) if selected else "(none)")
            )
            reply = "\n".join(lines)
            return self._finish_skill_turn(session, reply, selected=selected, persist=False)

        if command.kind == "clear":
            selected = []
            reply = "Cleared selected skills for this session."
            return self._finish_skill_turn(session, reply, selected=selected, persist=True)

        if command.kind in {"add", "remove"}:
            name = (command.name or "").strip()
            if not name:
                return self._finish_skill_turn(
                    session,
                    "Usage: /skill [list|clear|add <name>|remove <name>|<name>].",
                    selected=selected,
                    persist=False,
                )
            if name not in available:
                return self._finish_skill_turn(
                    session,
                    f"Skill '{name}' not found under skills/*.md.",
                    selected=selected,
                    persist=False,
                )
            if command.kind == "add":
                if name not in selected:
                    selected.append(name)
                reply = f"Selected skill '{name}' for this session."
            else:
                selected = [item for item in selected if item != name]
                reply = f"Removed skill '{name}' from this session."
            return self._finish_skill_turn(session, reply, selected=selected, persist=True)

        return self._finish_skill_turn(
            session,
            "Usage: /skill [list|clear|add <name>|remove <name>|<name>].",
            selected=selected,
            persist=False,
        )

    def _finish_skill_turn(
        self,
        session: Session,
        reply: str,
        *,
        selected: list[str],
        persist: bool,
    ) -> str:
        if persist:
            session.messages.append(
                self._make_message(
                    role="system",
                    content=format_skill_state_message(selected),
                    session=session,
                )
            )
        session.messages.append(
            self._make_message(role="assistant", content=reply, session=session)
        )
        self._record(
            session=session,
            event_type="session_finished",
            payload={"reason": "skill", "steps": 0},
        )
        session.turn_count += 1
        session.status = "running"
        self._maybe_auto_title(session)
        self._sessions.save(session)
        return reply

    def _apply_pending_steer(self, session: Session, *, step_index: int) -> None:
        """Inject queued steer messages before the next model call in this turn."""

        buffer = self._turn_steer
        if buffer is None:
            return
        pending = buffer.drain(session.id)
        for steer_index, text in enumerate(pending):
            self._record(
                session=session,
                event_type="user_steer_received",
                payload={
                    "turn_index": session.turn_count,
                    "step_index": step_index,
                    "user_input": text,
                    "steer_index": steer_index,
                },
            )
            session.messages.append(
                self._make_message(role="user", content=text, session=session)
            )

    def _inject_workspace_memory(self, session: Session) -> None:
        """Load workspace-scoped notes into the message list for this turn."""

        if self._memory is None or self._workspace_root is None:
            return
        key = workspace_memory_key(self._workspace_root)
        notes = self._memory.get(key)
        if not notes:
            return
        session.messages.append(
            self._make_message(
                role="system",
                content=format_workspace_memory_message(notes),
                session=session,
            )
        )
        self._record(
            session=session,
            event_type="workspace_memory_read",
            payload={
                "key": key,
                "line_count": notes.count("\n") + 1,
            },
        )

    def _inject_session_memory(self, session: Session) -> None:
        """Load session-scoped notes into the message list for this turn."""

        if self._memory is None:
            return
        key = session_memory_key(session.id)
        notes = self._memory.get(key)
        if not notes:
            return
        session.messages.append(
            self._make_message(
                role="system",
                content=format_memory_message(notes),
                session=session,
            )
        )
        self._record(
            session=session,
            event_type="memory_read",
            payload={
                "key": key,
                "line_count": notes.count("\n") + 1,
            },
        )

    def _write_remember_note(self, session: Session, body: str) -> None:
        """Append an explicit ``/remember`` note to session memory."""

        key = session_memory_key(session.id)
        line = format_remember_note(body)
        previous = self._memory.get(key) if self._memory else None
        updated = append_note(previous, line)
        self._memory.put(key, updated)  # type: ignore[union-attr]
        self._record(
            session=session,
            event_type="memory_written",
            payload={
                "key": key,
                "line": line,
                "line_count": updated.count("\n") + 1,
                "source": "remember",
            },
        )

    def _write_remember_global_note(self, session: Session, body: str) -> None:
        """Append an explicit ``/remember-global`` note to workspace memory."""

        if self._workspace_root is None:
            return
        key = workspace_memory_key(self._workspace_root)
        line = format_remember_global_note(body)
        previous = self._memory.get(key) if self._memory else None
        updated = append_note(previous, line)
        self._memory.put(key, updated)  # type: ignore[union-attr]
        self._record(
            session=session,
            event_type="workspace_memory_written",
            payload={
                "key": key,
                "line": line,
                "line_count": updated.count("\n") + 1,
                "source": "remember_global",
            },
        )

    # ------------------------------------------------------------------
    # compaction
    # ------------------------------------------------------------------

    def _maybe_compact(self, session: Session, *, trigger: str) -> None:
        """Compact older messages when the conversation exceeds the budget.

        Emits ``compaction_started`` and ``compaction_completed`` trace
        events around the work. The summary is produced by the
        loop-level summarizer when supplied; otherwise the
        deterministic fallback in :mod:`harnesslab.core.compaction`
        is used so eval and replay stay reproducible.
        """

        threshold = self._limits.compaction_threshold_tokens
        if not should_compact(session.messages, threshold_tokens=threshold):
            return
        self._do_compact(
            session,
            trigger=trigger,
            keep_last=self._limits.compaction_keep_last_messages,
        )

    def _do_compact(
        self,
        session: Session,
        *,
        trigger: str,
        keep_last: int,
        estimated_tokens_override: int | None = None,
    ) -> None:
        estimated = (
            estimated_tokens_override
            if estimated_tokens_override is not None
            else estimate_messages_tokens(session.messages)
        )
        self._record(
            session=session,
            event_type="compaction_started",
            payload={
                "trigger": trigger,
                "message_count": len(session.messages),
                "estimated_tokens": estimated,
                "threshold_tokens": self._limits.compaction_threshold_tokens,
                "keep_last": keep_last,
            },
        )

        new_messages, stats = compact_messages(
            session.messages,
            keep_last=keep_last,
            summarizer=self._summarizer,
            now=self._clock.now(),
            new_id=self._ids.new_id,
        )
        session.messages = new_messages

        self._record(
            session=session,
            event_type="compaction_completed",
            payload={
                "trigger": trigger,
                **stats,
                "estimated_tokens_after": estimate_messages_tokens(new_messages),
            },
        )

    def _call_model_with_overflow(
        self,
        session: Session,
        step_input: str,
        *,
        step_index: int = 0,
    ) -> tuple[Decision, datetime, datetime]:
        """Call the model; on overflow, force-compact and retry once.

        Adapters signal overflow by raising
        :class:`ModelOverflowError`. The first retry uses
        ``keep_last=max(1, configured // 2)`` so the next request
        is materially smaller. If the second call also overflows,
        the error propagates as a terminal ``final`` decision so
        the loop ends cleanly with a recognizable message instead
        of crashing the CLI.
        """

        try:
            return self._call_model(session, step_input, step_index=step_index)
        except ModelOverflowError as overflow:
            emergency_keep_last = max(
                1, self._limits.compaction_keep_last_messages // 2
            )
            self._do_compact(
                session,
                trigger="overflow",
                keep_last=emergency_keep_last,
                estimated_tokens_override=overflow.estimated_tokens,
            )
            try:
                return self._call_model(session, step_input, step_index=step_index)
            except ModelOverflowError as second:
                started = self._clock.now()
                ended = self._clock.now()
                msg = (
                    "Context window exceeded even after emergency compaction "
                    f"(keep_last={emergency_keep_last}). "
                    f"Reason: {second}"
                )
                return (
                    Decision(kind="final", assistant_message=msg),
                    started,
                    ended,
                )

    # ------------------------------------------------------------------
    # model + decision helpers
    # ------------------------------------------------------------------

    def _call_model(
        self,
        session: Session,
        user_input: str,
        *,
        step_index: int = 0,
    ) -> tuple[Decision, datetime, datetime]:
        started = self._clock.now()
        stream_reasoning_parts: list[str] = []
        sink = self._stream_sink

        def _stream_collector(kind: str, text: str, step_idx: int) -> None:
            if kind == "reasoning" and text:
                stream_reasoning_parts.append(text)
            if sink is not None:
                sink(kind, text, step_idx)

        token = bind_stream_sink(_stream_collector, step_index=step_index)
        try:
            set_stream_step_index(step_index)
            decision = self._model.decide(session, user_input)
        finally:
            reset_stream_sink(token)
        self._last_stream_reasoning = (
            "".join(stream_reasoning_parts).strip() or None
        )
        ended = self._clock.now()
        return decision, started, ended

    def _model_call_payload(
        self,
        decision: Decision,
        started_at: datetime,
        ended_at: datetime,
        session: Session,
    ) -> dict:
        raw_meta = self._model_raw_meta()
        payload: dict = {
            "model_name": type(self._model).__name__,
            "decision_kind": decision.kind,
            "latency_ms": (ended_at - started_at).total_seconds() * 1000.0,
        }
        payload.update(self._model_metadata(raw_meta))
        reasoning = self._model_reasoning_text()
        if reasoning:
            payload["reasoning_text"] = reasoning
        payload.update(self._model_prompt_payload())

        snapshot = make_conversation_snapshot(session.messages, self._limits)
        snapshot = merge_adapter_breakdown(snapshot, raw_meta)
        payload["context"] = snapshot.model_dump(exclude_none=True)
        return payload

    def _model_total_tokens(self) -> int | None:
        raw = self._model_raw_meta()
        if not raw:
            return None
        value = raw.get("total_tokens")
        if isinstance(value, int):
            return max(value, 0)
        return None

    def _model_raw_meta(self) -> dict | None:
        getter = getattr(self._model, "last_call_meta", None)
        if not callable(getter):
            return None
        raw = getter()
        return raw if isinstance(raw, dict) else None

    @staticmethod
    def _model_metadata(raw: dict | None) -> dict:
        if not raw:
            return {}
        allowed = {
            "model_name",
            "request_tokens",
            "response_tokens",
            "total_tokens",
            "provider",
            "reasoning_text",
        }
        return {k: raw[k] for k in allowed if k in raw}

    def _model_prompt_payload(self) -> dict:
        """Serialize the composed prompt from the last model call for trace/UI."""

        getter = getattr(self._model, "last_prompt", None)
        if not callable(getter):
            return {}
        composed = getter()
        if composed is None:
            return {}
        blocks = [
            {
                "name": block.name,
                "role": block.role,
                "origin": block.origin,
                "content": block.content,
                "char_count": len(block.content),
            }
            for block in composed.blocks
        ]
        wire_getter = getattr(self._model, "last_api_messages", None)
        api_messages: list[dict]
        if callable(wire_getter):
            wire = wire_getter()
            api_messages = wire if isinstance(wire, list) else composed.as_openai_messages()
        else:
            api_messages = composed.as_openai_messages()
        return {
            "prompt_blocks": blocks,
            "api_messages": api_messages,
        }

    def _reasoning_for_tool_persist(self) -> str | None:
        """Reasoning to store on a tool assistant row."""

        reasoning = self._model_reasoning_text()
        if reasoning is not None:
            return reasoning
        if self._model_thinking_likely():
            return ""
        return None

    def _model_thinking_likely(self) -> bool:
        """Best-effort hint for UI before the model returns."""

        mode = getattr(self._model, "_thinking_mode", None)
        if isinstance(mode, str) and mode not in {"", "disabled", "none"}:
            return True
        effort = getattr(self._model, "_reasoning_effort", None)
        if isinstance(effort, str) and effort not in {
            "",
            "disabled",
            "none",
            "minimal",
            "off",
        }:
            return True
        return False

    def _accumulate_model_cost(self, session: Session) -> None:
        raw = self._model_raw_meta()
        if not raw:
            return
        req_tokens = raw.get("request_tokens")
        resp_tokens = raw.get("response_tokens")
        cost = estimate_call_cost_usd(
            model_name=str(raw.get("model_name", "")) or None,
            request_tokens=req_tokens if isinstance(req_tokens, int) else None,
            response_tokens=resp_tokens if isinstance(resp_tokens, int) else None,
        )
        if cost > 0:
            session.budget_usage.cost_usd_total += cost

    def _maybe_create_checkpoint(self, session: Session, call: ToolCall) -> None:
        store = self._checkpoint_store
        root = self._workspace_root
        if store is None or root is None or call.name not in MUTATING_TOOLS:
            return
        snapshots = collect_file_snapshots(root, call.name, call.args)
        if not snapshots:
            return
        checkpoint_id = self._ids.new_id("cp")
        store.create(
            checkpoint_id=checkpoint_id,
            session_id=session.id,
            tool_name=call.name,
            tool_args=call.args,
            snapshots=snapshots,
        )
        self._record(
            session=session,
            event_type="checkpoint_created",
            payload={
                "checkpoint_id": checkpoint_id,
                "tool_name": call.name,
                "paths": sorted(snapshots.keys()),
            },
        )

    def _apply_decision(
        self,
        session: Session,
        decision: Decision,
    ) -> tuple[str, str]:
        """Apply one decision; return ``(user_visible_response, outcome)``.

        ``outcome`` is the short string written to the ``step_completed``
        trace event. It is one of ``final | ask_user | assistant | plan | tool |
        tool_invalid_args | tool_denied | tool_error | tool_ok``.
        """

        if decision.kind == "final":
            reply = decision.assistant_message or ""
            session.messages.append(
                self._make_message(
                    role="assistant",
                    content=reply,
                    session=session,
                    reasoning_text=self._model_reasoning_text(),
                    provider_extra=self._model_provider_extra(),
                )
            )
            return reply, "final"

        if decision.kind == "ask_user":
            reply = decision.assistant_message or ""
            session.messages.append(
                self._make_message(
                    role="assistant",
                    content=reply,
                    session=session,
                    reasoning_text=self._model_reasoning_text(),
                    provider_extra=self._model_provider_extra(),
                )
            )
            return reply, "ask_user"

        if decision.kind == "assistant":
            reply = decision.assistant_message or ""
            session.messages.append(
                self._make_message(
                    role="assistant",
                    content=reply,
                    session=session,
                    reasoning_text=self._model_reasoning_text(),
                    provider_extra=self._model_provider_extra(),
                )
            )
            return reply, "assistant"

        if decision.kind == "plan":
            reply = decision.assistant_message or ""
            extra = self._model_provider_extra() or {}
            extra = {**extra, "is_plan": True}
            session.messages.append(
                self._make_message(
                    role="assistant",
                    content=reply,
                    session=session,
                    reasoning_text=self._model_reasoning_text(),
                    provider_extra=extra,
                )
            )
            self._record(
                session=session,
                event_type="plan_emitted",
                payload={"plan": reply},
            )
            return reply, "plan"

        return self._apply_tool_decision(session, decision)

    def _maybe_emit_replan_reminder(
        self,
        *,
        session: Session,
        steps_used: int,
        max_steps: int,
    ) -> None:
        if self._replan_after_steps is None:
            return
        if steps_used <= 0 or steps_used >= max_steps:
            return
        if steps_used % self._replan_after_steps != 0:
            return
        reminder = (
            "Plan check: re-evaluate your current plan, summarize progress, "
            "and adjust next steps if needed."
        )
        session.messages.append(
            self._make_message(role="system", content=reminder, session=session)
        )
        self._record(
            session=session,
            event_type="plan_recheck_requested",
            payload={
                "steps_used": steps_used,
                "replan_after_steps": self._replan_after_steps,
            },
        )

    def _elapsed_ms(self, started_at: datetime) -> int:
        now = self._clock.now()
        return max(0, int((now - started_at).total_seconds() * 1000.0))

    def _session_wall_time_total(self, *, base_ms: int, turn_elapsed_ms: int) -> int:
        return max(0, base_ms + turn_elapsed_ms)

    def _enforce_budget(
        self,
        *,
        session: Session,
        turn_usage: TurnBudgetUsage,
        turn_started_at: datetime,
        session_wall_base: int,
    ) -> bool:
        if not self._budget_limits.enabled:
            return False
        turn_usage.wall_time_ms = self._elapsed_ms(turn_started_at)
        session.budget_usage.wall_time_ms_total = self._session_wall_time_total(
            base_ms=session_wall_base,
            turn_elapsed_ms=turn_usage.wall_time_ms,
        )
        breaches = detect_budget_breaches(
            limits=self._budget_limits,
            turn=turn_usage,
            session=session.budget_usage,
        )
        hard = [b for b in breaches if b.severity == "hard"]
        soft = [b for b in breaches if b.severity == "soft"]
        if not hard and not soft:
            session.budget_usage.last_budget_status = "ok"
            return False
        for breach in soft:
            if breach.dimension in turn_usage.soft_notified:
                continue
            turn_usage.soft_notified.add(breach.dimension)
            session.budget_usage.last_budget_status = "soft_exceeded"
            self._record_budget_event(session, breach, event_type="budget_soft_threshold")
        if not hard:
            return False
        session.budget_usage.last_budget_status = "hard_exceeded"
        for breach in hard:
            self._record_budget_event(session, breach, event_type="budget_hard_exceeded")
        self._record(
            session=session,
            event_type="budget_enforcement_action",
            payload={"action": self._budget_limits.action_on_hard},
        )
        return True

    def _record_budget_event(
        self,
        session: Session,
        breach: BudgetBreach,
        *,
        event_type: str,
    ) -> None:
        self._record(
            session=session,
            event_type=event_type,
            payload={
                "dimension": breach.dimension,
                "current": breach.current,
                "limit": breach.limit,
                "ratio": breach.ratio,
                "scope": breach.scope,
                "severity": breach.severity,
            },
        )

    def _budget_stop_message(self, session: Session) -> str:
        action = self._budget_limits.action_on_hard
        return (
            "Budget hard limit exceeded. "
            f"Action={action}. "
            f"Usage: llm_calls={session.budget_usage.llm_calls_total}, "
            f"tool_calls={session.budget_usage.tool_calls_total}, "
            f"tokens={session.budget_usage.tokens_total}, "
            f"wall_time_ms={session.budget_usage.wall_time_ms_total}."
        )

    def _model_reasoning_text(self) -> str | None:
        """Optional reasoning from the last model call (networked adapters)."""

        raw = self._model_raw_meta()
        if raw:
            reasoning = raw.get("reasoning_text")
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning.strip()
        stream = self._last_stream_reasoning
        if isinstance(stream, str) and stream.strip():
            return stream.strip()
        return None

    def _model_provider_extra(self) -> dict | None:
        """Opaque vendor payload from the last model call (e.g. thinking blocks)."""

        raw = self._model_raw_meta()
        if not raw:
            return None
        extra = raw.get("provider_extra")
        if isinstance(extra, dict) and extra:
            return extra
        return None

    def _apply_tool_decision(
        self,
        session: Session,
        decision: Decision,
    ) -> tuple[str, str]:
        call = self._make_tool_call(
            session_id=session.id,
            name=decision.tool_name or "",
            args=decision.tool_args,
        )

        schema_ok, schema_error = self._tools.validate_args(call)
        if not schema_ok:
            invalid_msg = f"Tool args invalid: {schema_error}"
            self._append_tool_exchange(session, call, invalid_msg)
            self._record(
                session=session,
                event_type="tool_invalid_args",
                payload={
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "args": call.args,
                    "error": schema_error,
                },
            )
            return invalid_msg, "tool_invalid_args"

        allowed, reason = self._policy.allow_tool(call)
        call.policy_decision = f"{'allow' if allowed else 'deny'}:{reason}"

        if not allowed:
            denied_msg = f"Tool denied by policy: {reason}"
            self._append_tool_exchange(session, call, denied_msg)
            self._record(
                session=session,
                event_type="tool_denied",
                payload={
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "args": call.args,
                    "policy_decision": call.policy_decision,
                    "reason": reason,
                },
            )
            _log.warning(
                "tool denied session=%s tool=%s reason=%s",
                session.id,
                call.name,
                reason,
            )
            return denied_msg, "tool_denied"

        call.started_at = self._clock.now()
        blocked = self._run_pre_tool_hooks(session, call)
        if blocked is not None:
            call.policy_decision = f"deny:hook:{blocked}"
            denied_msg = f"Tool denied by hook: {blocked}"
            self._append_tool_exchange(session, call, denied_msg)
            self._record(
                session=session,
                event_type="tool_denied",
                payload={
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "args": call.args,
                    "policy_decision": call.policy_decision,
                    "reason": f"hook:{blocked}",
                },
            )
            return denied_msg, "tool_denied"
        self._maybe_create_checkpoint(session, call)
        result = self._tools.execute(call)
        if result.ok and self._artifacts is not None:
            ext = maybe_externalize_tool_output(
                result.output,
                artifact_store=self._artifacts,
                ids=self._ids,
                session_id=session.id,
                threshold_bytes=self._limits.artifact_threshold_bytes,
            )
            result = ToolResult(
                ok=result.ok,
                output=ext.output,
                error=result.error,
                artifact_ref=ext.artifact_ref,
            )
        call.ended_at = self._clock.now()
        self._run_post_tool_hooks(session, call, result)

        tool_message = self._format_tool_message(call=call, result=result)
        self._append_tool_exchange(session, call, tool_message)
        self._record(
            session=session,
            event_type="tool_executed",
            payload=self._tool_executed_payload(call=call, result=result),
        )
        _log.info(
            "tool executed session=%s tool=%s ok=%s duration_ms=%s",
            session.id,
            call.name,
            result.ok,
            (
                (call.ended_at - call.started_at).total_seconds() * 1000.0
                if call.started_at and call.ended_at
                else None
            ),
        )
        return tool_message, "tool_ok" if result.ok else "tool_error"

    def _run_pre_tool_hooks(self, session: Session, call: ToolCall) -> str | None:
        runner = self._hook_runner
        if runner is None:
            return None
        for hook in runner.pre_hooks:
            self._record(
                session=session,
                event_type="hook_invoked",
                payload={
                    "phase": "pre_tool",
                    "name": hook.name,
                    "type": hook.hook_type,
                    "tool_name": call.name,
                },
            )
            try:
                decision = runner.run_pre(hook, call)
            except Exception as exc:  # noqa: BLE001
                self._record(
                    session=session,
                    event_type="hook_failed",
                    payload={
                        "phase": "pre_tool",
                        "name": hook.name,
                        "type": hook.hook_type,
                        "tool_name": call.name,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                continue
            if decision.action == "block":
                reason = decision.reason or f"blocked by hook '{hook.name}'"
                self._record(
                    session=session,
                    event_type="hook_blocked",
                    payload={
                        "phase": "pre_tool",
                        "name": hook.name,
                        "type": hook.hook_type,
                        "tool_name": call.name,
                        "reason": reason,
                    },
                )
                return reason
        return None

    def _run_post_tool_hooks(self, session: Session, call: ToolCall, result: ToolResult) -> None:
        runner = self._hook_runner
        if runner is None:
            return
        for hook in runner.post_hooks:
            self._record(
                session=session,
                event_type="hook_invoked",
                payload={
                    "phase": "post_tool",
                    "name": hook.name,
                    "type": hook.hook_type,
                    "tool_name": call.name,
                },
            )
            try:
                runner.run_post(hook, call, result)
            except Exception as exc:  # noqa: BLE001
                self._record(
                    session=session,
                    event_type="hook_failed",
                    payload={
                        "phase": "post_tool",
                        "name": hook.name,
                        "type": hook.hook_type,
                        "tool_name": call.name,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )

    def _tool_executed_payload(self, call: ToolCall, result: ToolResult) -> dict:
        duration_ms: float | None = None
        if call.started_at and call.ended_at:
            duration_ms = (call.ended_at - call.started_at).total_seconds() * 1000.0
        output_preview = result.output[:_TRACE_OUTPUT_PREVIEW_BYTES]
        truncated = len(result.output) > _TRACE_OUTPUT_PREVIEW_BYTES
        payload: dict = {
            "tool_call_id": call.id,
            "tool": call.name,
            "args": call.args,
            "policy_decision": call.policy_decision,
            "started_at": call.started_at.isoformat() if call.started_at else None,
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
            "duration_ms": duration_ms,
            "ok": result.ok,
            "error": result.error,
            "output_size": len(result.output),
            "output_preview": output_preview,
            "output_truncated": truncated,
        }
        if result.artifact_ref:
            payload["artifact_ref"] = result.artifact_ref
        return payload

    def _append_tool_exchange(
        self,
        session: Session,
        call: ToolCall,
        tool_content: str,
    ) -> None:
        """Record assistant ``tool_calls`` plus the tool result message."""

        session.messages.append(
            self._make_message(
                role="assistant",
                content="",
                session=session,
                tool_calls=_tool_calls_payload(call),
                reasoning_text=self._reasoning_for_tool_persist(),
                provider_extra=self._model_provider_extra(),
            )
        )
        session.messages.append(
            self._make_message(
                role="tool",
                content=tool_content,
                session=session,
                tool_call_id=call.id,
            )
        )

    def _make_message(
        self,
        role: str,
        content: str,
        session: Session,
        tool_call_id: str | None = None,
        tool_calls: list[dict] | None = None,
        reasoning_text: str | None = None,
        provider_extra: dict | None = None,
    ) -> Message:
        return Message(
            id=self._ids.new_id("msg"),
            role=role,  # type: ignore[arg-type]
            content=content,
            created_at=self._clock.now(),
            session_id=session.id,
            tool_call_id=tool_call_id,
            tool_calls=tool_calls,
            reasoning_text=reasoning_text,
            provider_extra=provider_extra,
        )

    def _make_tool_call(self, session_id: str, name: str, args: dict) -> ToolCall:
        return ToolCall(
            id=self._ids.new_id("tool"),
            name=name,
            args=args,
            session_id=session_id,
        )

    def _session_started_payload(self, *, goal: str) -> dict:
        payload: dict = {"goal": goal}
        profile = getattr(self._policy, "_shell_profile", None)
        if profile:
            payload["shell_profile"] = profile
        return payload

    def _record(self, session: Session, event_type: str, payload: dict) -> None:
        self._trace.record(
            TraceEvent(
                run_id=session.id,
                session_id=session.id,
                event_type=event_type,
                payload=payload,
                created_at=self._clock.now(),
            )
        )

    @staticmethod
    def _format_tool_message(call: ToolCall, result: ToolResult) -> str:
        if result.ok:
            return f"[tool:{call.name}] {result.output}"
        return f"[tool:{call.name}] failed: {result.error or 'unknown error'}"


def _tool_calls_payload(call: ToolCall) -> list[dict]:
    return [
        {
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.name,
                "arguments": json.dumps(call.args, ensure_ascii=False),
            },
        }
    ]
