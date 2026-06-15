import { describe, expect, it } from "vitest";
import { diffApiMessageLines, diffTextLines, messageTextContent } from "./promptLineDiff";

describe("promptLineDiff", () => {
  it("extracts string message content", () => {
    expect(messageTextContent({ role: "user", content: "hello" })).toBe("hello");
  });

  it("diffs changed lines", () => {
    const lines = diffTextLines("a\nb", "a\nc");
    expect(lines).toContain("  a");
    expect(lines).toContain("- b");
    expect(lines).toContain("+ c");
  });

  it("diffs api message arrays", () => {
    const lines = diffApiMessageLines(
      [{ role: "user", content: "one" }],
      [{ role: "user", content: "two" }]
    );
    expect(lines.some((line) => line.includes("api_messages[0]"))).toBe(true);
    expect(lines).toContain("- one");
    expect(lines).toContain("+ two");
  });
});
