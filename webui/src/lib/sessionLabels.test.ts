import { describe, expect, it } from "vitest";
import { sessionLabel, sessionListMeta, sessionStatusLabel } from "./sessionLabels";
import type { SessionSummary } from "./schemas";

function summary(partial: Partial<SessionSummary>): SessionSummary {
  return {
    id: "ses_x",
    goal: "demo",
    title: null,
    status: "running",
    turn_count: 0,
    step_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    last_step_at: null,
    parent_session_id: null,
    message_count: 0,
    ...partial,
  };
}

describe("sessionLabels", () => {
  it("maps known session statuses", () => {
    expect(sessionStatusLabel("done")).toBe("已完成");
    expect(sessionStatusLabel("running")).toBe("进行中");
    expect(sessionStatusLabel("waiting_user")).toBe("等待回复");
  });

  it("formats list meta with turns and message count", () => {
    expect(
      sessionListMeta(
        summary({ status: "done", turn_count: 3, message_count: 48 })
      )
    ).toBe("已完成 · 3 轮 · 48 条消息");
  });

  it("prefers title then goal for display label", () => {
    expect(sessionLabel(summary({ title: "My chat" }))).toBe("My chat");
    expect(sessionLabel(summary({ title: null, goal: "Fix bug" }))).toBe("Fix bug");
    expect(sessionLabel(summary({ title: "", goal: "", id: "ses_abcdef12" }))).toBe("ses_abcd");
  });
});
