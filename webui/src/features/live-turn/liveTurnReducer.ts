import type { MessageItem, ToolCard } from "../../lib/schemas";

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
