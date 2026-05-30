import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { I18nProvider } from "../../lib/i18n";
import { ChatScrollArea } from "./ChatScrollArea";

afterEach(() => {
  cleanup();
});

function renderScroll(ui: ReactElement) {
  return render(
    <I18nProvider locale="en" onLocaleChange={() => {}}>
      {ui}
    </I18nProvider>
  );
}

describe("ChatScrollArea", () => {
  it("does not show new-messages pill when user scrolls up without new content", () => {
    renderScroll(
      <ChatScrollArea scrollSignal="turn-1" resetKey="session-a">
        <div style={{ height: 1200 }}>long content</div>
      </ChatScrollArea>
    );

    const area = screen.getByTestId("chat-scroll-area");
    Object.defineProperty(area, "clientHeight", { value: 300, configurable: true });
    Object.defineProperty(area, "scrollHeight", { value: 1200, configurable: true });
    area.scrollTop = 0;
    fireEvent.scroll(area);

    expect(screen.queryByRole("button", { name: "New messages" })).toBeNull();
  });

  it("shows new-messages pill after content grows while scrolled up", () => {
    const { rerender } = renderScroll(
      <ChatScrollArea scrollSignal="turn-1" resetKey="session-a">
        <div style={{ height: 1200 }}>long content</div>
      </ChatScrollArea>
    );

    const area = screen.getByTestId("chat-scroll-area");
    Object.defineProperty(area, "clientHeight", { value: 300, configurable: true });
    Object.defineProperty(area, "scrollHeight", { value: 1200, configurable: true });
    area.scrollTop = 0;
    fireEvent.scroll(area);

    rerender(
      <I18nProvider locale="en" onLocaleChange={() => {}}>
        <ChatScrollArea scrollSignal="turn-2" resetKey="session-a">
          <div style={{ height: 1400 }}>longer content</div>
        </ChatScrollArea>
      </I18nProvider>
    );

    expect(screen.getByRole("button", { name: "New messages" })).toBeTruthy();
  });

  it("hides new-messages pill after clicking jump", () => {
    const { rerender } = renderScroll(
      <ChatScrollArea scrollSignal="turn-1" resetKey="session-a">
        <div style={{ height: 1200 }}>long content</div>
      </ChatScrollArea>
    );

    const area = screen.getByTestId("chat-scroll-area");
    Object.defineProperty(area, "clientHeight", { value: 300, configurable: true });
    Object.defineProperty(area, "scrollHeight", { value: 1200, configurable: true });
    area.scrollTop = 0;
    fireEvent.scroll(area);

    rerender(
      <I18nProvider locale="en" onLocaleChange={() => {}}>
        <ChatScrollArea scrollSignal="turn-2" resetKey="session-a">
          <div style={{ height: 1400 }}>longer content</div>
        </ChatScrollArea>
      </I18nProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "New messages" }));
    expect(screen.queryByRole("button", { name: "New messages" })).toBeNull();
  });
});
