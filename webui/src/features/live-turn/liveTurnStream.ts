import type { LiveTurnState } from "./liveTurnReducer";

export type StreamDeltaKind = "reasoning" | "assistant";

/** Append token-level SSE deltas to the in-flight turn. */
export function applyLiveTurnDelta(
  state: LiveTurnState | null,
  kind: StreamDeltaKind,
  text: string
): LiveTurnState | null {
  if (!state || !text) return state;

  if (kind === "reasoning") {
    const thoughts = [...state.thoughts];
    let idx = thoughts.findIndex((t) => t.status === "thinking");
    if (idx < 0) {
      thoughts.push({
        stepIndex: state.stepIndex,
        status: "thinking",
        startedAt: Date.now(),
        text: "",
      });
      idx = thoughts.length - 1;
    }
    const row = thoughts[idx];
    thoughts[idx] = { ...row, text: `${row.text || ""}${text}` };
    return { ...state, thoughts, thinkingLikely: true, phase: "running" };
  }

  return {
    ...state,
    assistantText: `${state.assistantText}${text}`,
    phase: state.phase === "pending" ? "answering" : state.phase === "running" ? "answering" : state.phase,
  };
}
