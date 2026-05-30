import { describe, expect, it } from "vitest";
import type { MessageItem, ToolCard } from "./schemas";
import type { ThoughtEntry } from "../features/live-turn/liveTurnReducer";
import {
  assistantDisplayBody,
  isChatMessageVisible,
  isLiveTurnVisible,
} from "./messageVisibility";

const toolOnlyAssistant: MessageItem = {
  id: "a1",
  role: "assistant",
  content: "",
  reasoning_text: "plan step",
  created_at: "2026-05-28T12:00:00.000Z",
};

const textAssistant: MessageItem = {
  id: "a2",
  role: "assistant",
  content: "Final answer.",
  created_at: "2026-05-28T12:00:00.000Z",
};

const tools: ToolCard[] = [{ tool: "grep", ok: true, output_preview: "hit" }];
const thoughts: ThoughtEntry[] = [
  {
    stepIndex: 0,
    status: "done",
    text: "Planning…",
    startedAt: Date.parse("2026-05-28T12:00:00.000Z"),
  },
];

describe("messageVisibility", () => {
  it("hides thought-only assistant rows when showThinking is false", () => {
    expect(
      isChatMessageVisible(toolOnlyAssistant, { showThinking: false, showTools: false })
    ).toBe(false);
  });

  it("shows thought-only assistant rows when showThinking is true", () => {
    expect(
      isChatMessageVisible(toolOnlyAssistant, { showThinking: true, showTools: false })
    ).toBe(true);
  });

  it("shows assistant text regardless of thought/tool prefs", () => {
    expect(
      isChatMessageVisible(textAssistant, { showThinking: false, showTools: false })
    ).toBe(true);
  });

  it("shows tool-only rows when showTools is true", () => {
    expect(
      isChatMessageVisible(
        { ...toolOnlyAssistant, reasoning_text: undefined },
        { showThinking: false, showTools: true },
        { tools }
      )
    ).toBe(true);
  });

  it("strips inline thinking tags from display body", () => {
    const body = assistantDisplayBody({
      id: "a3",
      role: "assistant",
      content: "<thinking>secret</thinking>\nAnswer.",
      created_at: "2026-05-28T12:00:00.000Z",
    });
    expect(body).toBe("Answer.");
  });

  it("hides completed live turns with only hidden activity", () => {
    expect(
      isLiveTurnVisible(
        {
          assistantText: "",
          thoughts,
          tools,
          childRuns: [],
          phase: "done",
        },
        { showThinking: false, showTools: false }
      )
    ).toBe(false);
  });
});
