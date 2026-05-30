import { describe, expect, it } from "vitest";
import {
  activityEntryFromTrace,
  buildActivityFeed,
  isActivityTraceEvent,
} from "./activityFeed";
import type { TraceEventItem } from "../../lib/schemas";

function trace(eventType: string, payload: Record<string, unknown>): TraceEventItem {
  return {
    run_id: "run_1",
    session_id: "ses_1",
    event_type: eventType,
    payload,
    created_at: "2026-05-28T00:00:00Z",
  };
}

describe("activityFeed", () => {
  it("recognizes activity trace events", () => {
    expect(isActivityTraceEvent("tool_executed")).toBe(true);
    expect(isActivityTraceEvent("user_steer_received")).toBe(true);
    expect(isActivityTraceEvent("sub_agent_spawned")).toBe(true);
    expect(isActivityTraceEvent("model_call")).toBe(false);
  });

  it("redacts tool args and truncates output preview", () => {
    const entry = activityEntryFromTrace(
      trace("tool_executed", {
        tool: "grep",
        ok: true,
        args: { pattern: "foo", path: "src" },
        output_preview: "line one\nline two",
        duration_ms: 120,
      })
    );
    expect(entry?.label).toBe("grep · ok · 120ms");
    expect(entry?.detail).toContain("2 args");
    expect(entry?.detail).toContain("line one");
    expect(entry?.detail).not.toContain("pattern");
  });

  it("builds newest-first feed with cap", () => {
    const feed = buildActivityFeed(
      [
        trace("step_started", { step_index: 0 }),
        trace("tool_executed", { tool: "read_file", ok: true, args: {} }),
        trace("tool_denied", { tool: "shell", reason: "not allowed" }),
      ],
      2
    );
    expect(feed).toHaveLength(2);
    expect(feed[0]?.kind).toBe("tool_denied");
  });
});
