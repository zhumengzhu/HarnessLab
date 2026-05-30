import { describe, expect, it } from "vitest";
import { spanColorGenerator, spanServiceColor } from "./spanColor";

describe("spanServiceColor", () => {
  it("returns stable color for the same service name", () => {
    spanColorGenerator.clear();
    const a = spanServiceColor("harnesslab");
    const b = spanServiceColor("harnesslab");
    expect(a).toBe(b);
    expect(a).toMatch(/^var\(--span-color-\d+\)$/);
  });

  it("assigns different colors to different services", () => {
    spanColorGenerator.clear();
    const a = spanServiceColor("harnesslab");
    const b = spanServiceColor("other-svc");
    expect(a).not.toBe(b);
  });
});
