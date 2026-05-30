import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChildSessionsPanel } from "./ChildSessionsPanel";
import type { SessionSummary } from "../../lib/schemas";

const baseSession = (overrides: Partial<SessionSummary>): SessionSummary => ({
  id: "ses_x",
  goal: "goal",
  title: null,
  status: "running",
  turn_count: 0,
  step_count: 0,
  created_at: "2026-01-01T00:00:00Z",
  last_step_at: null,
  parent_session_id: null,
  message_count: 0,
  ...overrides,
});

describe("ChildSessionsPanel", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders nothing when no parent or children", () => {
    const { container } = render(
      <ChildSessionsPanel
        parentSession={null}
        childSessions={[]}
        selectedSessionId={null}
        onSelectSession={() => {}}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it("navigates to parent and child sessions", () => {
    const onSelect = vi.fn();
    const parent = baseSession({ id: "ses_parent", goal: "supervisor" });
    const child = baseSession({
      id: "ses_child",
      goal: "research subtask",
      parent_session_id: "ses_parent",
      step_count: 2,
    });

    render(
      <ChildSessionsPanel
        parentSession={parent}
        childSessions={[child]}
        selectedSessionId="ses_child"
        onSelectSession={onSelect}
      />
    );

    expect(screen.getByText("子 Agent")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /←/ }));
    expect(onSelect).toHaveBeenCalledWith("ses_parent");
  });
});
