import { describe, expect, it } from "vitest";
import { isLiveSpan, mergeTraceSpans } from "./liveSpans";
import type { SpanRecordItem, SpanStartedPayload } from "./schemas";

const now = "2026-05-31T12:00:00.000Z";

function completed(partial: Partial<SpanRecordItem> & Pick<SpanRecordItem, "span_id" | "name">): SpanRecordItem {
  return {
    trace_id: "t1",
    session_id: "s1",
    turn_index: 0,
    start_time: now,
    end_time: now,
    duration_ms: 10,
    attributes: {},
    parent_span_id: null,
    ...partial,
  };
}

describe("mergeTraceSpans", () => {
  it("includes in-flight started spans before completion", () => {
    const started: SpanStartedPayload = {
      trace_id: "t1",
      span_id: "turn1",
      name: "harnesslab.turn",
      session_id: "s1",
      turn_index: 0,
      parent_span_id: null,
    };
    const merged = mergeTraceSpans([], [], [started], { turn1: Date.parse(now) });
    expect(merged).toHaveLength(1);
    expect(isLiveSpan(merged[0])).toBe(true);
  });

  it("completed span replaces started placeholder", () => {
    const started: SpanStartedPayload = {
      trace_id: "t1",
      span_id: "llm1",
      name: "llm.generate",
      session_id: "s1",
      parent_span_id: "step1",
    };
    const done = completed({ span_id: "llm1", name: "llm.generate", duration_ms: 120 });
    const merged = mergeTraceSpans([], [done], [started], { llm1: Date.parse(now) });
    expect(merged).toHaveLength(1);
    expect(isLiveSpan(merged[0])).toBe(false);
    expect(merged[0].duration_ms).toBe(120);
  });
});
