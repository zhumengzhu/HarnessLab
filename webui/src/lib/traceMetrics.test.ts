import { describe, expect, it } from "vitest";
import { spanMatchesDeepQuery } from "./spanSearch";
import { aggregateTurnLlmMetrics } from "./traceMetrics";
import type { SpanRecordItem } from "./schemas";

describe("aggregateTurnLlmMetrics", () => {
  it("sums llm.generate token metrics for one trace", () => {
    const spans: SpanRecordItem[] = [
      {
        trace_id: "t1",
        span_id: "a",
        name: "llm.generate",
        session_id: "s1",
        turn_index: 0,
        start_time: "",
        end_time: "",
        duration_ms: 1,
        attributes: {},
        metrics: { input_tokens: 10, output_tokens: 5, total_tokens: 15, cost_usd: 0.001 },
      },
      {
        trace_id: "t1",
        span_id: "b",
        name: "llm.generate",
        session_id: "s1",
        turn_index: 0,
        start_time: "",
        end_time: "",
        duration_ms: 1,
        attributes: {},
        metrics: { input_tokens: 20, output_tokens: 8, total_tokens: 28 },
      },
      {
        trace_id: "t2",
        span_id: "c",
        name: "llm.generate",
        session_id: "s1",
        turn_index: 1,
        start_time: "",
        end_time: "",
        duration_ms: 1,
        attributes: {},
        metrics: { total_tokens: 99 },
      },
    ];
    const summary = aggregateTurnLlmMetrics(spans, "t1");
    expect(summary.llmCalls).toBe(2);
    expect(summary.inputTokens).toBe(30);
    expect(summary.outputTokens).toBe(13);
    expect(summary.totalTokens).toBe(43);
    expect(summary.costUsd).toBeCloseTo(0.001);
  });
});

describe("spanMatchesDeepQuery", () => {
  it("matches prompt block content in metrics", () => {
    const span: SpanRecordItem = {
      trace_id: "t1",
      span_id: "a",
      name: "llm.generate",
      session_id: "s1",
      turn_index: 0,
      start_time: "",
      end_time: "",
      duration_ms: 1,
      attributes: {},
      metrics: {
        prompt_blocks: [{ name: "identity", content: "You are HarnessLab assistant" }],
      },
    };
    expect(spanMatchesDeepQuery(span, "HarnessLab assistant")).toBe(true);
    expect(spanMatchesDeepQuery(span, "missing phrase")).toBe(false);
  });
});
