"""Stable span attribute keys (Observability v2).

Keys are pinned here so adapters and the loop do not drift. GenAI names
follow OpenTelemetry incubating semconv; renames require a doc + baseline PR.
See ``docs/architecture/observability-v2.md``.
"""

from __future__ import annotations

# --- OpenTelemetry Resource (process-scoped) ---
SERVICE_NAME = "service.name"
SERVICE_VERSION = "service.version"
SERVICE_INSTANCE_ID = "service.instance.id"
DEPLOYMENT_ENVIRONMENT = "deployment.environment"

# --- HarnessLab resource ---
HARNESSLAB_WORKSPACE = "harnesslab.workspace"

# --- Span correlation (every span) ---
HARNESSLAB_SESSION_ID = "harnesslab.session.id"
HARNESSLAB_TURN_INDEX = "harnesslab.turn.index"
HARNESSLAB_PARENT_SESSION_ID = "harnesslab.parent_session.id"

# --- Turn root ---
HARNESSLAB_SESSION_GOAL = "harnesslab.session.goal"
HARNESSLAB_USER_INPUT_PREVIEW = "harnesslab.user_input.preview"
HARNESSLAB_MAX_STEPS = "harnesslab.max_steps"
HARNESSLAB_SHELL_PROFILE = "harnesslab.shell_profile"
HARNESSLAB_TERMINAL_REASON = "harnesslab.terminal.reason"
HARNESSLAB_STEPS_USED = "harnesslab.steps.used"

# --- Step ---
HARNESSLAB_STEP_INDEX = "harnesslab.step.index"
HARNESSLAB_STEP_REASON = "harnesslab.step.reason"
HARNESSLAB_STEP_OUTCOME = "harnesslab.step.outcome"

# --- GenAI (incubating semconv) ---
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"

# --- LLM ---
HARNESSLAB_DECISION_KIND = "harnesslab.decision.kind"
HARNESSLAB_THINKING_ENABLED = "harnesslab.thinking.enabled"
HARNESSLAB_FAILOVER_ATTEMPTS = "harnesslab.failover.attempts"

# --- Tool ---
HARNESSLAB_TOOL_NAME = "harnesslab.tool.name"
HARNESSLAB_TOOL_CALL_ID = "harnesslab.tool_call.id"
HARNESSLAB_TOOL_OK = "harnesslab.tool.ok"
HARNESSLAB_POLICY_DECISION = "harnesslab.policy.decision"
HARNESSLAB_HOOK_NAME = "harnesslab.hook.name"
HARNESSLAB_HOOK_TYPE = "harnesslab.hook.type"
HARNESSLAB_HOOK_PHASE = "harnesslab.hook.phase"

# --- Compaction ---
HARNESSLAB_COMPACTION_TRIGGER = "harnesslab.compaction.trigger"
HARNESSLAB_COMPACTION_KEEP_LAST = "harnesslab.compaction.keep_last"
HARNESSLAB_COMPACTION_MESSAGES_BEFORE = "harnesslab.compaction.messages_before"
HARNESSLAB_COMPACTION_MESSAGES_AFTER = "harnesslab.compaction.messages_after"
HARNESSLAB_COMPACTION_THRESHOLD_TOKENS = "harnesslab.compaction.threshold_tokens"

# --- Skill ---
HARNESSLAB_SKILL_NAME = "harnesslab.skill.name"
HARNESSLAB_SKILL_COMMAND = "harnesslab.skill.command"
HARNESSLAB_SKILL_TASK_PREVIEW = "harnesslab.skill.task_preview"

# --- Sub-agent ---
HARNESSLAB_CHILD_SESSION_ID = "harnesslab.child_session.id"
HARNESSLAB_SUB_AGENT_GOAL = "harnesslab.sub_agent.goal"
HARNESSLAB_SUB_AGENT_MAX_STEPS = "harnesslab.sub_agent.max_steps"
HARNESSLAB_LINK_KIND = "harnesslab.link.kind"

# --- Span names (normative) ---
SPAN_TURN = "harnesslab.turn"
SPAN_STEP = "harnesslab.step"
SPAN_LLM_GENERATE = "llm.generate"
SPAN_LLM_TITLE = "llm.title"
SPAN_CONTEXT_COMPACT = "context.compact"
SPAN_SKILL_INVOKE = "skill.invoke"
SPAN_SKILL_COMMAND = "skill.command"
SPAN_SLASH_REMEMBER = "slash.remember"
SPAN_SUB_AGENT_RUN = "sub_agent.run"
SPAN_SESSION_CHECKPOINT = "session.checkpoint"
