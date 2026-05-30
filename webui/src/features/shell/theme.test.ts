import { describe, expect, it } from "vitest";
import { applyUiTheme } from "./theme";

describe("applyUiTheme", () => {
  it("sets data-hl-theme on documentElement", () => {
    applyUiTheme("light");
    expect(document.documentElement.getAttribute("data-hl-theme")).toBe("light");
    applyUiTheme("dark");
    expect(document.documentElement.getAttribute("data-hl-theme")).toBe("dark");
  });
});
