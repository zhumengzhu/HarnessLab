import { describe, expect, it } from "vitest";
import { createLiveTurn } from "./liveTurnReducer";
import { applyLiveTurnDelta } from "./liveTurnStream";

describe("applyLiveTurnDelta", () => {
  it("appends reasoning text to active thinking row", () => {
    let turn = createLiveTurn("hi");
    turn = applyLiveTurnDelta(turn, "reasoning", "step ")!;
    turn = applyLiveTurnDelta(turn, "reasoning", "one")!;
    expect(turn.thoughts[0]?.text).toBe("step one");
    expect(turn.thinkingLikely).toBe(true);
  });

  it("appends assistant answer text", () => {
    let turn = createLiveTurn("hi");
    turn = applyLiveTurnDelta(turn, "assistant", "Hello")!;
    expect(turn.assistantText).toBe("Hello");
    expect(turn.phase).toBe("answering");
  });
});
