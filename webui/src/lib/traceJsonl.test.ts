import { describe, expect, it } from "vitest";
import { filterTraceEvents, traceEventsToJsonl } from "./traceJsonl";
import type { TraceEventItem } from "./schemas";

const sample: TraceEventItem[] = [
  {
    run_id: "run_1",
    session_id: "ses_1",
    event_type: "user_input_received",
    payload: { message: "hello" },
    created_at: "2026-05-30T12:00:00+00:00",
  },
  {
    run_id: "run_1",
    session_id: "ses_1",
    event_type: "tool_executed",
    payload: { tool: "grep", ok: true },
    created_at: "2026-05-30T12:00:01+00:00",
  },
];

describe("traceJsonl", () => {
  it("serializes events as JSONL lines", () => {
    const jsonl = traceEventsToJsonl(sample);
    const lines = jsonl.trim().split("\n");
    expect(lines).toHaveLength(2);
    expect(JSON.parse(lines[0]).event_type).toBe("user_input_received");
    expect(JSON.parse(lines[1]).payload.tool).toBe("grep");
  });

  it("filters by event type or payload", () => {
    expect(filterTraceEvents(sample, "tool_executed")).toHaveLength(1);
    expect(filterTraceEvents(sample, "grep")).toHaveLength(1);
    expect(filterTraceEvents(sample, "")).toHaveLength(2);
  });
});
