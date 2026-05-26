import { describe, expect, it } from "vitest";
import { shouldSubmitComposerOnEnter } from "./composerEnter";

describe("shouldSubmitComposerOnEnter", () => {
  it("submits on plain Enter", () => {
    expect(shouldSubmitComposerOnEnter("Enter", false, false)).toBe(true);
  });

  it("does not submit on Shift+Enter", () => {
    expect(shouldSubmitComposerOnEnter("Enter", true, false)).toBe(false);
  });

  it("does not submit while IME is composing", () => {
    expect(shouldSubmitComposerOnEnter("Enter", false, true)).toBe(false);
  });
});
