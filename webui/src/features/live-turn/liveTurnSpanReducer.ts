import type {
  SpanEventPayload,
  SpanLinkPayload,
  SpanRecordItem,
  SpanStartedPayload,
  ToolCard,
} from "../../lib/schemas";
import { toolCardFromSpan } from "../../lib/toolCardFromSpan";
import type { ChildAgentRun, LiveTurnPhase, LiveTurnState, ThoughtEntry } from "./liveTurnReducer";

export type LiveSpanSignal =
  | { kind: "started"; payload: SpanStartedPayload }
  | { kind: "completed"; record: SpanRecordItem }
  | { kind: "event"; payload: SpanEventPayload }
  | { kind: "link"; payload: SpanLinkPayload };

function childSessionId(payload: { child_session_id?: string; attributes?: Record<string, unknown> }): string | null {
  if (payload.child_session_id) return payload.child_session_id;
  const linked = payload.attributes?.["harnesslab.child_session.id"];
  return typeof linked === "string" && linked ? linked : null;
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

type AgentSlice = {
  phase: LiveTurnPhase;
  stepIndex: number;
  thoughts: ThoughtEntry[];
  tools: ToolCard[];
  assistantText: string;
  thinkingLikely: boolean;
};

function childToSlice(child: ChildAgentRun): AgentSlice {
  return {
    phase: child.phase,
    stepIndex: child.stepIndex,
    thoughts: child.thoughts,
    tools: child.tools,
    assistantText: child.assistantText,
    thinkingLikely: false,
  };
}

function applySliceToChild(child: ChildAgentRun, slice: AgentSlice): ChildAgentRun {
  return {
    ...child,
    phase: slice.phase,
    stepIndex: slice.stepIndex,
    thoughts: slice.thoughts,
    tools: slice.tools,
    assistantText: slice.assistantText,
  };
}

function reduceStarted(slice: AgentSlice, payload: SpanStartedPayload): AgentSlice {
  const attrs = payload.attributes ?? {};
  if (payload.name === "harnesslab.step") {
    const stepIndex =
      typeof attrs["harnesslab.step.index"] === "number"
        ? (attrs["harnesslab.step.index"] as number)
        : slice.stepIndex;
    return { ...slice, phase: "running", stepIndex };
  }
  if (payload.name === "llm.generate") {
    const stepIndex =
      typeof attrs["harnesslab.step.index"] === "number"
        ? (attrs["harnesslab.step.index"] as number)
        : slice.stepIndex;
    const thinkingLikely = Boolean(attrs["harnesslab.thinking.enabled"]);
    const thoughts = [...slice.thoughts];
    if (!thoughts.some((t) => t.stepIndex === stepIndex && t.status === "thinking")) {
      thoughts.push({ stepIndex, status: "thinking", startedAt: Date.now() });
    }
    return { ...slice, phase: "running", stepIndex, thinkingLikely, thoughts };
  }
  if (payload.name === "sub_agent.run") {
    return { ...slice, phase: "running" };
  }
  return slice;
}

function reduceCompleted(slice: AgentSlice, record: SpanRecordItem): AgentSlice {
  const metrics = record.metrics ?? {};
  const attrs = record.attributes ?? {};

  if (record.name === "llm.generate") {
    const stepIndex =
      typeof attrs["harnesslab.step.index"] === "number"
        ? (attrs["harnesslab.step.index"] as number)
        : slice.stepIndex;
    const latencyMs =
      typeof metrics.latency_ms === "number" ? metrics.latency_ms : undefined;
    const reasoning =
      typeof metrics.reasoning_text === "string" ? metrics.reasoning_text : undefined;
    const thoughts = slice.thoughts.map((t) => {
      if (t.stepIndex === stepIndex && t.status === "thinking") {
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
    const decisionKind = attrs["harnesslab.decision.kind"];
    if (
      decisionKind === "final" ||
      decisionKind === "ask_user" ||
      decisionKind === "assistant" ||
      decisionKind === "plan"
    ) {
      return { ...slice, thoughts, phase: "answering" };
    }
    return { ...slice, thoughts, phase: "running" };
  }

  if (record.name.startsWith("tool.") && !record.name.startsWith("tool.hooks.")) {
    const card = toolCardFromSpan(record);
    if (!card) return slice;
    if (card.ok === false && attrs["harnesslab.policy.decision"]) {
      return { ...slice, tools: [...slice.tools, card], phase: "running" };
    }
    return { ...slice, tools: [...slice.tools, card], phase: "running" };
  }

  if (record.name === "harnesslab.turn") {
    const reason = String(attrs["harnesslab.terminal.reason"] ?? "");
    if (reason === "max_steps") {
      const hint =
        "Step budget reached. Send **continue** to keep going or ask for a partial summary.";
      return {
        ...slice,
        assistantText: slice.assistantText || hint,
        phase: "answering",
      };
    }
    return { ...slice, phase: "complete" };
  }

  if (record.name === "sub_agent.run") {
    return { ...slice, phase: "complete" };
  }

  return slice;
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

export function reduceLiveTurnSpan(
  state: LiveTurnState | null,
  signal: LiveSpanSignal
): LiveTurnState | null {
  if (!state) return null;

  if (signal.kind === "link") {
    const childId = childSessionId(signal.payload);
    if (!childId) return state;
    const goal =
      typeof signal.payload.attributes?.["harnesslab.sub_agent.goal"] === "string"
        ? String(signal.payload.attributes["harnesslab.sub_agent.goal"])
        : "sub-agent";
    const child = state.childRuns.find((c) => c.childSessionId === childId) ?? createChildRun(childId, goal);
    return upsertChildRun(state, { ...child, phase: "running" });
  }

  if (signal.kind === "started") {
    const childId = childSessionId(signal.payload);
    if (childId) {
      let child =
        state.childRuns.find((c) => c.childSessionId === childId) ??
        createChildRun(
          childId,
          String(signal.payload.attributes?.["harnesslab.sub_agent.goal"] ?? "sub-agent")
        );
      const next = reduceStarted(childToSlice(child), signal.payload);
      child = applySliceToChild(child, next);
      return upsertChildRun(state, child);
    }
    const next = reduceStarted(
      {
        phase: state.phase,
        stepIndex: state.stepIndex,
        thoughts: state.thoughts,
        tools: state.tools,
        assistantText: state.assistantText,
        thinkingLikely: state.thinkingLikely,
      },
      signal.payload
    );
    return { ...state, ...next };
  }

  if (signal.kind === "completed") {
    const record = signal.record;
    const childId = record.child_session_id ?? childSessionId(record);
    if (childId) {
      let child =
        state.childRuns.find((c) => c.childSessionId === childId) ??
        createChildRun(childId, "sub-agent");
      const next = reduceCompleted(childToSlice(child), record);
      child = applySliceToChild(child, next);
      return upsertChildRun(state, child);
    }
    const next = reduceCompleted(
      {
        phase: state.phase,
        stepIndex: state.stepIndex,
        thoughts: state.thoughts,
        tools: state.tools,
        assistantText: state.assistantText,
        thinkingLikely: state.thinkingLikely,
      },
      record
    );
    return { ...state, ...next };
  }

  if (signal.kind === "event" && signal.payload.name === "decision.applied") {
    const kind = String(signal.payload.attributes?.kind ?? "");
    const assistantMessage =
      typeof signal.payload.attributes?.assistant_message === "string"
        ? signal.payload.attributes.assistant_message
        : "";
    if (kind === "final" || kind === "ask_user" || kind === "assistant" || kind === "plan") {
      return { ...state, assistantText: assistantMessage, phase: "answering" };
    }
  }

  return state;
}
