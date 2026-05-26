import type { ThoughtEntry } from "../features/live-turn/liveTurnReducer";

/** Attach provider reasoning to the best matching thought row. */
export function applyReasoningText(
  thoughts: ThoughtEntry[],
  reasoning: string,
  stepIndex: number
): ThoughtEntry[] {
  const text = reasoning.trim();
  if (!text) return thoughts;

  let applied = false;
  const updated = thoughts.map((t) => {
    if (applied) return t;
    if (t.stepIndex === stepIndex && !t.text?.trim()) {
      applied = true;
      return { ...t, status: "done" as const, text };
    }
    return t;
  });
  if (applied) return updated;

  for (let i = updated.length - 1; i >= 0; i -= 1) {
    if (!updated[i].text?.trim()) {
      const copy = [...updated];
      copy[i] = { ...copy[i], status: "done", text };
      return copy;
    }
  }

  return [
    ...updated,
    {
      stepIndex,
      status: "done" as const,
      text,
      startedAt: Date.now(),
    },
  ];
}

export function thoughtsWithText(thoughts: ThoughtEntry[]): ThoughtEntry[] {
  return thoughts.filter((t) => Boolean(t.text?.trim()));
}

export function mergeMessageReasoningIntoThoughts(
  thoughts: ThoughtEntry[],
  reasoningText: string | undefined,
  createdAt: string
): ThoughtEntry[] {
  const reasoning = reasoningText?.trim();
  if (!reasoning) return thoughtsWithText(thoughts);

  if (!thoughts.length) {
    return [
      {
        stepIndex: 0,
        status: "done",
        text: reasoning,
        startedAt: new Date(createdAt).getTime(),
      },
    ];
  }

  if (thoughts.some((t) => t.text?.trim())) {
    return thoughtsWithText(thoughts);
  }

  return thoughts.map((t, idx) =>
    idx === thoughts.length - 1 ? { ...t, status: "done" as const, text: reasoning } : t
  );
}
