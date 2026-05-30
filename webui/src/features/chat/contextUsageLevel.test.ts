import { describe, expect, it } from "vitest";
import { getContextUsageLevel } from "./contextUsageLevel";

describe("getContextUsageLevel", () => {
  it("returns healthy below 70%", () => {
    expect(getContextUsageLevel(0)).toBe("healthy");
    expect(getContextUsageLevel(0.69)).toBe("healthy");
  });

  it("returns warn above 70% and up to 90%", () => {
    expect(getContextUsageLevel(0.71)).toBe("warn");
    expect(getContextUsageLevel(0.9)).toBe("warn");
  });

  it("returns danger above 90%", () => {
    expect(getContextUsageLevel(0.91)).toBe("danger");
    expect(getContextUsageLevel(1)).toBe("danger");
  });
});
