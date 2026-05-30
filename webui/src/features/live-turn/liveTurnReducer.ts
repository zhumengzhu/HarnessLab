import type { MessageItem, ToolCard, TraceEventItem } from "../../lib/schemas";
import { toolCardFromTraceEvent } from "../../lib/toolCardFromTrace";

export type ThoughtEntry = {
  stepIndex: number;
  status: "thinking" | "done";
  text?: string;
  startedAt: number;
  durationMs?: number;
};

export type LiveTurnPhase =
  | "pending"
  | "running"
  | "answering"
  | "complete"
  | "stopped"
  | "error";

export type ChildAgentRun = {
  childSessionId: string;
  goal: string;
  phase: LiveTurnPhase;
  stepIndex: number;
  thoughts: ThoughtEntry[];
  tools: ToolCard[];
  assistantText: string;
};

export type LiveTurnState = {
  id: string;
  userMessage: MessageItem;
  phase: LiveTurnPhase;
  stepIndex: number;
  thoughts: ThoughtEntry[];
  tools: ToolCard[];
  assistantText: string;
  thinkingLikely: boolean;
  childRuns: ChildAgentRun[];
};

export function createLiveTurn(userText: string): LiveTurnState {
  const now = new Date().toISOString();
  return {
    id: `live-${Date.now()}`,
    userMessage: {
      id: `pending-user-${Date.now()}`,
      role: "user",
      content: userText,
      created_at: now,
    },
    phase: "pending",
    stepIndex: 0,
    thoughts: [],
    tools: [],
    assistantText: "",
    thinkingLikely: false,
    childRuns: [],
  };
}

function createChildRun(childSessionId: string, goal: string): ChildAgentRun {
  return {
    childSessionId,
    goal,
    phase: "running",
    stepIndex: 0,
    thoughts: [],
    tools: [],
    assistantText: "",
  };
}

export function eventChildSessionId(evt: TraceEventItem): string | null {
  const top = (evt as TraceEventItem & { child_session_id?: string }).child_session_id;
  if (top) return top;
  if (evt.event_type === "sub_agent_spawned" || evt.event_type === "sub_agent_completed") {
    const id = evt.payload.child_session_id;
    return typeof id === "string" && id ? id : null;
  }
  return null;
}

type AgentSlice = {
  phase: LiveTurnPhase;
  stepIndex: number;
  thoughts: ThoughtEntry[];
  tools: ToolCard[];
  assistantText: string;
  thinkingLikely?: boolean;
};

function reduceAgentSlice(
  state: AgentSlice,
  evt: TraceEventItem,
  options?: { thinkingLikelyDefault?: boolean }
): AgentSlice {
  const payload = evt.payload;
  let thinkingLikely = state.thinkingLikely ?? options?.thinkingLikelyDefault ?? false;

  if (evt.event_type === "step_started") {
    const stepIndex =
      typeof payload.step_index === "number" ? payload.step_index : state.stepIndex;
    return { ...state, phase: "running", stepIndex, thinkingLikely };
  }

  if (evt.event_type === "model_call_started") {
    const stepIndex =
      typeof payload.step_index === "number" ? payload.step_index : state.stepIndex;
    thinkingLikely = Boolean(payload.thinking_likely ?? thinkingLikely);
    const thoughts = [...state.thoughts];
    const active = thoughts.find(
      (t) => t.stepIndex === stepIndex && t.status === "thinking"
    );
    if (!active) {
      thoughts.push({
        stepIndex,
        status: "thinking",
        startedAt: Date.now(),
      });
    }
    return {
      ...state,
      phase: "running",
      stepIndex,
      thinkingLikely,
      thoughts,
    };
  }

  if (evt.event_type === "model_call") {
    const stepIndex = state.stepIndex;
    const latencyMs =
      typeof payload.latency_ms === "number" ? payload.latency_ms : undefined;
    const reasoning =
      typeof payload.reasoning_text === "string" ? payload.reasoning_text : undefined;
    let matched = false;
    const thoughts = state.thoughts.map((t) => {
      if (t.stepIndex === stepIndex && t.status === "thinking") {
        matched = true;
        return {
          ...t,
          status: "done" as const,
          text: reasoning ?? t.text,
          durationMs: latencyMs ?? Math.max(0, Date.now() - t.startedAt),
        };
      }
      if (t.status === "thinking") {
        return {
          ...t,
          status: "done" as const,
          durationMs: Math.max(0, Date.now() - t.startedAt),
        };
      }
      return t;
    });
    if (!matched && (reasoning || latencyMs != null)) {
      thoughts.push({
        stepIndex,
        status: "done",
        text: reasoning,
        startedAt: Date.now() - (latencyMs ?? 0),
        durationMs: latencyMs,
      });
    }
    return { ...state, thoughts, phase: "running", thinkingLikely };
  }

  if (evt.event_type === "tool_executed") {
    const card = toolCardFromTraceEvent(evt);
    if (!card) return state;
    return { ...state, tools: [...state.tools, card], phase: "running", thinkingLikely };
  }

  if (evt.event_type === "tool_denied") {
    const card: ToolCard = {
      tool: String(payload.tool || "tool"),
      ok: false,
      error: String(payload.reason || payload.policy_decision || "denied"),
      output_preview: "",
      output_truncated: false,
      duration_ms: null,
    };
    return { ...state, tools: [...state.tools, card], phase: "running", thinkingLikely };
  }

  if (evt.event_type === "decision_made") {
    const kind = String(payload.kind || "");
    const assistantMessage =
      typeof payload.assistant_message === "string" ? payload.assistant_message : "";
    if (kind === "final" || kind === "ask_user" || kind === "assistant" || kind === "plan") {
      return {
        ...state,
        assistantText: assistantMessage,
        phase: "answering",
        thinkingLikely,
      };
    }
    return { ...state, phase: "running", thinkingLikely };
  }

  if (evt.event_type === "session_finished") {
    const reason = String(payload.reason || "");
    if (reason === "max_steps") {
      const hint =
        "Step budget reached. Send **continue** to keep going or ask for a partial summary.";
      return {
        ...state,
        assistantText: state.assistantText || hint,
        phase: "answering",
        thinkingLikely,
      };
    }
    return { ...state, phase: "complete", thinkingLikely };
  }

  if (evt.event_type === "sub_agent_completed") {
    const preview =
      typeof payload.final_response_preview === "string"
        ? payload.final_response_preview
        : "";
    return {
      ...state,
      assistantText: state.assistantText || preview,
      phase: "complete",
      thinkingLikely,
    };
  }

  return { ...state, thinkingLikely };
}

function upsertChildRun(state: LiveTurnState, child: ChildAgentRun): LiveTurnState {
  const idx = state.childRuns.findIndex((c) => c.childSessionId === child.childSessionId);
  if (idx < 0) {
    return { ...state, childRuns: [...state.childRuns, child] };
  }
  const childRuns = [...state.childRuns];
  childRuns[idx] = child;
  return { ...state, childRuns };
}

function reduceChildEvent(
  state: LiveTurnState,
  evt: TraceEventItem,
  childSessionId: string
): LiveTurnState {
  let child =
    state.childRuns.find((c) => c.childSessionId === childSessionId) ??
    createChildRun(childSessionId, "sub-agent");

  if (evt.event_type === "sub_agent_spawned") {
    const goal = typeof evt.payload.goal === "string" ? evt.payload.goal : child.goal;
    child = { ...createChildRun(childSessionId, goal), ...child, goal, phase: "running" };
    return upsertChildRun(state, child);
  }

  const next = reduceAgentSlice(child, evt);
  child = {
    ...child,
    phase: next.phase,
    stepIndex: next.stepIndex,
    thoughts: next.thoughts,
    tools: next.tools,
    assistantText: next.assistantText,
  };
  return upsertChildRun(state, child);
}

export function reduceLiveTurn(
  state: LiveTurnState | null,
  evt: TraceEventItem
): LiveTurnState | null {
  if (!state) return null;

  if (evt.event_type === "sub_agent_spawned") {
    const childSessionId = eventChildSessionId(evt);
    if (!childSessionId) return state;
    return reduceChildEvent(state, evt, childSessionId);
  }

  const childSessionId = eventChildSessionId(evt);
  if (childSessionId) {
    return reduceChildEvent(state, evt, childSessionId);
  }

  const next = reduceAgentSlice(
    {
      phase: state.phase,
      stepIndex: state.stepIndex,
      thoughts: state.thoughts,
      tools: state.tools,
      assistantText: state.assistantText,
      thinkingLikely: state.thinkingLikely,
    },
    evt,
    { thinkingLikelyDefault: state.thinkingLikely }
  );
  return {
    ...state,
    phase: next.phase,
    stepIndex: next.stepIndex,
    thoughts: next.thoughts,
    tools: next.tools,
    assistantText: next.assistantText,
    thinkingLikely: next.thinkingLikely ?? state.thinkingLikely,
  };
}

export function finalizeLiveTurn(state: LiveTurnState | null): LiveTurnState | null {
  if (!state) return null;
  const childRuns = state.childRuns.map((c) =>
    c.phase === "running" || c.phase === "pending" ? { ...c, phase: "complete" as const } : c
  );
  return { ...state, phase: "complete", childRuns };
}

export function stopLiveTurn(state: LiveTurnState | null): LiveTurnState | null {
  if (!state) return null;
  const thoughts = state.thoughts.map((t) =>
    t.status === "thinking"
      ? {
          ...t,
          status: "done" as const,
          durationMs: Math.max(0, Date.now() - t.startedAt),
        }
      : t
  );
  const childRuns = state.childRuns.map((c) => ({
    ...c,
    thoughts: c.thoughts.map((t) =>
      t.status === "thinking"
        ? {
            ...t,
            status: "done" as const,
            durationMs: Math.max(0, Date.now() - t.startedAt),
          }
        : t
    ),
    phase: c.phase === "running" || c.phase === "pending" ? ("stopped" as const) : c.phase,
  }));
  return { ...state, thoughts, childRuns, phase: "stopped" };
}
