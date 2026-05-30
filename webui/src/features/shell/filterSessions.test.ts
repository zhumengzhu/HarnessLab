import { describe, expect, it } from "vitest";
import { filterSessions } from "./filterSessions";
import type { SessionSummary } from "../../lib/schemas";

function summary(partial: Partial<SessionSummary>): SessionSummary {
  return {
    id: "ses_x",
    goal: "demo goal",
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

describe("filterSessions", () => {
  const sessions = [
    summary({ id: "ses_a", title: "Alpha chat", status: "done" }),
    summary({ id: "ses_b", goal: "research web", status: "running" }),
    summary({
      id: "ses_c",
      title: "Child run",
      status: "waiting_user",
      parent_session_id: "ses_a",
    }),
  ];

  it("returns all sessions when query and status are empty", () => {
    expect(filterSessions(sessions)).toHaveLength(3);
  });

  it("filters by title, goal, id, or localized status label", () => {
    expect(filterSessions(sessions, { query: "alpha" }).map((s) => s.id)).toEqual(["ses_a"]);
    expect(filterSessions(sessions, { query: "research" }).map((s) => s.id)).toEqual(["ses_b"]);
    expect(filterSessions(sessions, { query: "ses_c" }).map((s) => s.id)).toEqual(["ses_c"]);
    expect(filterSessions(sessions, { query: "已完成" }).map((s) => s.id)).toEqual(["ses_a"]);
  });

  it("filters by status bucket", () => {
    expect(filterSessions(sessions, { status: "done" }).map((s) => s.id)).toEqual(["ses_a"]);
    expect(filterSessions(sessions, { status: "child" }).map((s) => s.id)).toEqual(["ses_c"]);
  });

  it("pins selected session when filters would hide it", () => {
    const filtered = filterSessions(sessions, {
      query: "alpha",
      status: "running",
      pinSessionId: "ses_a",
    });
    expect(filtered.map((s) => s.id)).toEqual(["ses_a"]);
  });
});
