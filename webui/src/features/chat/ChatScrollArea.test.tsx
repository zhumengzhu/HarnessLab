import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ChatScrollArea } from "./ChatScrollArea";

afterEach(() => {
  cleanup();
});

describe("ChatScrollArea", () => {
  it("shows jump button after scrolling up", () => {
    render(
      <ChatScrollArea scrollSignal="turn-1">
        <div style={{ height: 1200 }}>long content</div>
      </ChatScrollArea>
    );

    const area = screen.getByTestId("chat-scroll-area");
    Object.defineProperty(area, "clientHeight", { value: 300, configurable: true });
    Object.defineProperty(area, "scrollHeight", { value: 1200, configurable: true });
    area.scrollTop = 0;
    fireEvent.scroll(area);

    expect(screen.getByRole("button", { name: "跳到最新" })).toBeTruthy();
  });

  it("hides jump button after clicking latest", () => {
    render(
      <ChatScrollArea scrollSignal="turn-1">
        <div style={{ height: 1200 }}>long content</div>
      </ChatScrollArea>
    );

    const area = screen.getByTestId("chat-scroll-area");
    Object.defineProperty(area, "clientHeight", { value: 300, configurable: true });
    Object.defineProperty(area, "scrollHeight", { value: 1200, configurable: true });
    area.scrollTop = 0;
    fireEvent.scroll(area);

    fireEvent.click(screen.getByRole("button", { name: "跳到最新" }));
    expect(screen.queryByRole("button", { name: "跳到最新" })).toBeNull();
  });
});
