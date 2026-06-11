import { describe, expect, it } from "vitest";
import { buildTraceHtml } from "./traceHtmlExport";
import type { SpanRecordItem } from "./schemas";

const sampleSpan: SpanRecordItem = {
  span_id: "span_a",
  trace_id: "trace_a",
  session_id: "ses_a",
  turn_index: 0,
  name: "harnesslab.step",
  parent_span_id: null,
  start_time: "2026-06-07T10:00:00.000Z",
  end_time: "2026-06-07T10:00:01.000Z",
  duration_ms: 1000,
  status: "OK",
  attributes: { "harnesslab.step.index": 0 },
  metrics: {},
  events: [],
  links: [],
};

describe("buildTraceHtml", () => {
  it("embeds session id and span data", () => {
    const html = buildTraceHtml([sampleSpan], "ses_a", "2026-06-07T12:00:00.000Z");
    expect(html).toContain("<!DOCTYPE html>");
    expect(html).toContain("ses_a");
    expect(html).toContain("harnesslab.step");
    expect(html).toContain('"span_id":"span_a"');
    expect(html).toContain('id="search"');
  });
});
