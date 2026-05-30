import { describe, expect, it } from "vitest";
import {
  CHAT_NEAR_BOTTOM_PX,
  isNearBottom,
  scrollElementToBottom,
  shouldCollapseComposerChrome,
  shouldExpandComposerChrome,
} from "./useChatScroll";

function mockScrollElement(
  scrollHeight: number,
  clientHeight: number,
  scrollTop: number
): HTMLElement {
  const el = document.createElement("div");
  Object.defineProperties(el, {
    scrollHeight: { value: scrollHeight, configurable: true },
    clientHeight: { value: clientHeight, configurable: true },
    scrollTop: { value: scrollTop, writable: true, configurable: true },
  });
  return el;
}

describe("useChatScroll helpers", () => {
  it("detects near-bottom within threshold", () => {
    const el = mockScrollElement(1000, 400, 520);
    expect(isNearBottom(el)).toBe(true);
    expect(isNearBottom(el, CHAT_NEAR_BOTTOM_PX)).toBe(true);
  });

  it("detects when user scrolled away from bottom", () => {
    const el = mockScrollElement(1000, 400, 100);
    expect(isNearBottom(el)).toBe(false);
  });

  it("scrolls element to bottom", () => {
    const el = mockScrollElement(900, 300, 0);
    scrollElementToBottom(el);
    expect(el.scrollTop).toBe(600);
  });

  it("collapses composer chrome when scrolling down away from bottom", () => {
    expect(shouldExpandComposerChrome(120, 80, false)).toBe(false);
    expect(shouldCollapseComposerChrome(120, 80, false)).toBe(true);
    expect(shouldExpandComposerChrome(500, 520, true)).toBe(true);
    expect(shouldCollapseComposerChrome(500, 520, true)).toBe(false);
  });
});
