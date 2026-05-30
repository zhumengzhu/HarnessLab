import { describe, expect, it } from "vitest";
import { filterSpans, spansToJsonl } from "./traceJsonl";
import type { SpanRecordItem } from "./schemas";

const sample: SpanRecordItem[] = [
  {
    trace_id: "t1",
    span_id: "s1",
    name: "harnesslab.turn",
    session_id: "ses1",
    turn_index: 0,
    start_time: "2026-05-30T12:00:00+00:00",
    end_time: "2026-05-30T12:00:01+00:00",
    duration_ms: 1000,
    attributes: {},
  },
  {
    trace_id: "t1",
    span_id: "s2",
    parent_span_id: "s1",
    name: "tool.grep",
    session_id: "ses1",
    turn_index: 0,
    start_time: "2026-05-30T12:00:00+00:00",
    end_time: "2026-05-30T12:00:00+00:00",
    duration_ms: 50,
    attributes: { "harnesslab.tool.name": "grep", "harnesslab.tool.ok": true },
    metrics: { output_preview: "match" },
  },
];

describe("traceJsonl spans", () => {
  it("serializes spans as JSONL lines", () => {
    const jsonl = spansToJsonl(sample);
    const lines = jsonl.trim().split("\n");
    expect(lines).toHaveLength(2);
    expect(JSON.parse(lines[0]).name).toBe("harnesslab.turn");
    expect(JSON.parse(lines[1]).name).toBe("tool.grep");
  });

  it("filters by span name or payload", () => {
    expect(filterSpans(sample, "tool.grep")).toHaveLength(1);
    expect(filterSpans(sample, "grep")).toHaveLength(1);
    expect(filterSpans(sample, "")).toHaveLength(2);
  });
});
