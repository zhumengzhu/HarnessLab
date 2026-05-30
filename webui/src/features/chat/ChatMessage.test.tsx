import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { MessageItem, ToolCard } from "../../lib/schemas";
import { ChatMessage } from "./ChatMessage";
import { I18nProvider } from "../../lib/i18n";
import {
  ChatDisplayProvider,
  type ChatDisplayPreferences,
} from "./chatDisplayPreferences";
import type { ThoughtEntry } from "../live-turn/liveTurnReducer";

const assistantMessage: MessageItem = {
  id: "msg-1",
  role: "assistant",
  content: "Final answer for the user.",
  created_at: "2026-05-28T12:00:00.000Z",
};

const toolCards: ToolCard[] = [
  {
    tool: "grep",
    ok: true,
    output_preview: "src/main.py:42",
    duration_ms: 88,
  },
];

const thoughtEntries: ThoughtEntry[] = [
  {
    stepIndex: 0,
    status: "done",
    text: "Plan: read files then summarize.",
    startedAt: Date.parse("2026-05-28T12:00:00.000Z"),
    durationMs: 120,
  },
];

function renderWithDisplay(
  ui: ReactElement,
  overrides: Partial<ChatDisplayPreferences> = {}
) {
  const value: ChatDisplayPreferences = {
    activityDisplay: "detailed",
    setActivityDisplay: () => {},
    chatTextSize: "md",
    setChatTextSize: () => {},
    showThinking: true,
    setShowThinking: () => {},
    showTools: true,
    setShowTools: () => {},
    ...overrides,
  };
  return render(
    <I18nProvider locale="en" onLocaleChange={() => {}}>
      <ChatDisplayProvider value={value}>{ui}</ChatDisplayProvider>
    </I18nProvider>
  );
}

describe("ChatMessage", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders assistant body without runtime errors", () => {
    renderWithDisplay(
      <ChatMessage
        message={assistantMessage}
        toolCards={toolCards}
        thoughtEntries={thoughtEntries}
      />
    );
    expect(screen.getByText("HarnessLab")).toBeTruthy();
    expect(screen.getByText("Final answer for the user.")).toBeTruthy();
  });

  it("hides entire assistant bubble when only thoughts are hidden", () => {
    const thoughtOnly: MessageItem = {
      id: "msg-thought",
      role: "assistant",
      content: "",
      reasoning_text: "hidden plan",
      created_at: "2026-05-28T12:00:00.000Z",
    };
    const { container } = renderWithDisplay(
      <ChatMessage message={thoughtOnly} thoughtEntries={thoughtEntries} />,
      { showThinking: false, showTools: false }
    );
    expect(container.querySelector(".chat-bubble-row")).toBeNull();
  });

  it("hides thinking blocks when showThinking is false", () => {
    const { container } = renderWithDisplay(
      <ChatMessage
        message={assistantMessage}
        toolCards={toolCards}
        thoughtEntries={thoughtEntries}
      />,
      { showThinking: false }
    );
    expect(container.querySelector(".thinking-block")).toBeNull();
    expect(screen.getByText("Final answer for the user.")).toBeTruthy();
  });

  it("shows thinking blocks when showThinking is true", () => {
    const { container } = renderWithDisplay(
      <ChatMessage
        message={assistantMessage}
        toolCards={toolCards}
        thoughtEntries={thoughtEntries}
      />,
      { showThinking: true }
    );
    const thinking = container.querySelector(".thinking-block");
    expect(thinking).toBeTruthy();
    expect(within(thinking as HTMLElement).getByText("Plan: read files then summarize.")).toBeTruthy();
  });

  it("hides tool cards when showTools is false", () => {
    const { container } = renderWithDisplay(
      <ChatMessage
        message={assistantMessage}
        toolCards={toolCards}
        thoughtEntries={thoughtEntries}
      />,
      { showTools: false }
    );
    expect(container.querySelector(".chat-msg-tools")).toBeNull();
  });

  it("shows tool cards when showTools is true", () => {
    renderWithDisplay(
      <ChatMessage
        message={assistantMessage}
        toolCards={toolCards}
        thoughtEntries={thoughtEntries}
      />,
      { showTools: true }
    );
    expect(screen.getByText(/grep · ok/)).toBeTruthy();
  });
});
