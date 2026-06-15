import { describe, expect, it } from "vitest";
import { replayFocusFromDivergence } from "./replayFocus";

describe("replayFocusFromDivergence", () => {
  it("parses turn index and span name from node diff path", () => {
    const focus = replayFocusFromDivergence({
      index: 1,
      kind: "node",
      detail: "turn[2]/tool.fetch_url[0]: name: 'tool.read_file' != 'tool.fetch_url'",
    });
    expect(focus).toEqual({ turnIndex: 2, spanNameHint: "tool.fetch_url" });
  });

  it("falls back to divergence index when detail has no turn path", () => {
    const focus = replayFocusFromDivergence({
      index: 3,
      kind: "turn_count",
      detail: "original has 2 turn(s), replayed has 1",
    });
    expect(focus).toEqual({ turnIndex: 3 });
  });
});
