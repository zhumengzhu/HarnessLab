import type { MessageItem, ToolCard, TraceEventItem } from "../../lib/schemas";
import { applyReasoningText } from "../../lib/thoughtUtils";
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

export type LiveTurnState = {
  id: string;
  userMessage: MessageItem;
  phase: LiveTurnPhase;
  stepIndex: number;
  thoughts: ThoughtEntry[];
  tools: ToolCard[];
  assistantText: string;
  thinkingLikely: boolean;
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
  };
}

export function reduceLiveTurn(
  state: LiveTurnState | null,
  evt: TraceEventItem
): LiveTurnState | null {
  if (!state) return null;

  const payload = evt.payload;

  if (evt.event_type === "step_started") {
    const stepIndex =
      typeof payload.step_index === "number" ? payload.step_index : state.stepIndex;
    return { ...state, phase: "running", stepIndex };
  }

  if (evt.event_type === "model_call_started") {
    const stepIndex =
      typeof payload.step_index === "number" ? payload.step_index : state.stepIndex;
    const thinkingLikely = Boolean(payload.thinking_likely ?? state.thinkingLikely);
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
    return { ...state, thoughts, phase: "running" };
  }

  if (evt.event_type === "tool_executed") {
    const card = toolCardFromTraceEvent(evt);
    if (!card) return state;
    return { ...state, tools: [...state.tools, card], phase: "running" };
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
    return { ...state, tools: [...state.tools, card], phase: "running" };
  }

  if (evt.event_type === "decision_made") {
    const kind = String(payload.kind || "");
    const assistantMessage =
      typeof payload.assistant_message === "string" ? payload.assistant_message : "";
    const reasoning =
      typeof payload.reasoning_text === "string" ? payload.reasoning_text : undefined;
    let thoughts = state.thoughts;
    if (reasoning?.trim()) {
      thoughts = applyReasoningText(state.thoughts, reasoning, state.stepIndex);
    }
    if (kind === "final" || kind === "ask_user" || kind === "assistant" || kind === "plan") {
      return {
        ...state,
        thoughts,
        assistantText: assistantMessage,
        phase: "answering",
      };
    }
    return { ...state, thoughts, phase: "running" };
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
      };
    }
  }

  return state;
}

export function finalizeLiveTurn(state: LiveTurnState | null): LiveTurnState | null {
  if (!state) return null;
  return { ...state, phase: "complete" };
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
  return { ...state, thoughts, phase: "stopped" };
}
