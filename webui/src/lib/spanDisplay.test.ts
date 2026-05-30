import { describe, expect, it } from "vitest";
import {
  spanDisplayLabel,
  spanDisplaySubtitle,
  spanMatchesQuery,
  spanOperationHint,
  spanOperationName,
} from "./spanDisplay";
import type { SpanRecordItem } from "./schemas";

function span(
  overrides: Partial<SpanRecordItem> & Pick<SpanRecordItem, "name">
): SpanRecordItem {
  return {
    trace_id: "t1",
    span_id: "s1",
    session_id: "ses1",
    turn_index: 0,
    start_time: "2026-05-31T10:00:00.000Z",
    end_time: "2026-05-31T10:00:01.000Z",
    duration_ms: 1000,
    attributes: {},
    ...overrides,
  };
}

describe("spanOperationName", () => {
  it("returns canonical domain.action span names", () => {
    expect(spanOperationName(span({ name: "llm.generate" }))).toBe("llm.generate");
    expect(spanOperationName(span({ name: "tool.read_file" }))).toBe("tool.read_file");
    expect(spanOperationName(span({ name: "harnesslab.step" }))).toBe("harnesslab.step");
  });
});

describe("spanOperationHint", () => {
  it("shows step index and model as hints", () => {
    expect(
      spanOperationHint(
        span({
          name: "harnesslab.step",
          attributes: { "harnesslab.step.index": 2 },
        })
      )
    ).toBe("index=2");
    expect(
      spanOperationHint(
        span({
          name: "llm.generate",
          attributes: { "gen_ai.request.model": "deepseek-v4-flash" },
        })
      )
    ).toBe("deepseek-v4-flash");
  });
});

describe("spanDisplayLabel", () => {
  it("maps native span names to operator labels for chat surfaces", () => {
    expect(spanDisplayLabel(span({ name: "llm.generate" }))).toBe("LLM");
    expect(
      spanDisplayLabel(
        span({
          name: "tool.read_file",
          attributes: { "harnesslab.tool.name": "read_file" },
        })
      )
    ).toBe("read_file");
  });
});

describe("spanDisplaySubtitle", () => {
  it("shows decision kind for llm spans", () => {
    expect(
      spanDisplaySubtitle(
        span({
          name: "llm.generate",
          attributes: { "harnesslab.decision.kind": "final" },
        })
      )
    ).toBe("final");
  });
});

describe("spanMatchesQuery", () => {
  it("matches operation name and attributes", () => {
    const record = span({
      name: "tool.web_search",
      attributes: { "harnesslab.tool.name": "web_search", "harnesslab.tool.ok": true },
    });
    expect(spanMatchesQuery(record, "tool.web_search")).toBe(true);
    expect(spanMatchesQuery(record, "web_search")).toBe(true);
    expect(spanMatchesQuery(record, "missing")).toBe(false);
  });
});
