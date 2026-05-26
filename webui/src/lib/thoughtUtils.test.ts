import { describe, expect, it } from "vitest";
import { applyReasoningText, mergeMessageReasoningIntoThoughts } from "./thoughtUtils";
import type { ThoughtEntry } from "../features/live-turn/liveTurnReducer";

describe("thoughtUtils", () => {
  it("fills reasoning on already-done thought after model_call", () => {
    const thoughts: ThoughtEntry[] = [
      {
        stepIndex: 0,
        status: "done",
        startedAt: Date.now() - 1000,
        durationMs: 1000,
      },
    ];
    const updated = applyReasoningText(thoughts, "hidden chain", 0);
    expect(updated[0].text).toBe("hidden chain");
  });

  it("merges message reasoning when trace thoughts are empty", () => {
    const merged = mergeMessageReasoningIntoThoughts(
      [{ stepIndex: 0, status: "done", startedAt: 0, durationMs: 500 }],
      "from message api",
      "2026-05-25T00:00:00.000Z"
    );
    expect(merged[0].text).toBe("from message api");
  });
});
