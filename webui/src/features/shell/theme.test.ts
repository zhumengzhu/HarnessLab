import { describe, expect, it } from "vitest";
import { applyUiTheme, resolveColorScheme, resolveUiTheme } from "./theme";

describe("applyUiTheme", () => {
  it("sets data-hl-theme on documentElement", () => {
    applyUiTheme("claw-light");
    expect(document.documentElement.getAttribute("data-hl-theme")).toBe("claw-light");
    applyUiTheme("classic-dark");
    expect(document.documentElement.getAttribute("data-hl-theme")).toBe("classic-dark");
  });

  it("maps legacy light/dark to claw variants", () => {
    applyUiTheme("light");
    expect(document.documentElement.getAttribute("data-hl-theme")).toBe("claw-light");
    applyUiTheme("dark");
    expect(document.documentElement.getAttribute("data-hl-theme")).toBe("claw-dark");
  });
});

describe("resolveUiTheme", () => {
  it("combines family and explicit scheme", () => {
    expect(resolveUiTheme("claw", "dark")).toBe("claw-dark");
    expect(resolveUiTheme("classic", "light")).toBe("classic-light");
  });

  it("maps system to a concrete scheme", () => {
    const resolved = resolveUiTheme("claw", "system");
    expect(resolved === "claw-dark" || resolved === "claw-light").toBe(true);
  });
});

describe("resolveColorScheme", () => {
  it("returns explicit dark or light unchanged", () => {
    expect(resolveColorScheme("dark")).toBe("dark");
    expect(resolveColorScheme("light")).toBe("light");
  });
});
