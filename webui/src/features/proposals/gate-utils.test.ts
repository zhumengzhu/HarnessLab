import { describe, expect, it } from "vitest";
import { summarizeGateOutput } from "./gate-utils";

describe("summarizeGateOutput", () => {
  it("returns original output when under tail limit", () => {
    const input = "line1\nline2";
    expect(summarizeGateOutput(input, 5)).toBe(input);
  });

  it("returns tail-only output with omitted count", () => {
    const input = Array.from({ length: 6 }, (_, i) => `line${i + 1}`).join("\n");
    expect(summarizeGateOutput(input, 2)).toBe("...(4 lines omitted)\nline5\nline6");
  });
});
