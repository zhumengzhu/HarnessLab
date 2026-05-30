import { describe, expect, it } from "vitest";
import { buildSpanTree, filterFlatSpanRows, flattenSpanTree, groupSpansByTrace } from "./spanTree";
import type { SpanRecordItem } from "./schemas";

function span(
  overrides: Partial<SpanRecordItem> & Pick<SpanRecordItem, "span_id" | "name">
): SpanRecordItem {
  return {
    trace_id: "trace1",
    session_id: "ses1",
    turn_index: 0,
    start_time: "2026-05-31T10:00:00.000Z",
    end_time: "2026-05-31T10:00:01.000Z",
    duration_ms: 1000,
    attributes: {},
    parent_span_id: null,
    ...overrides,
  };
}

describe("buildSpanTree", () => {
  it("builds hierarchy from parent_span_id", () => {
    const turn = span({
      span_id: "turn1",
      name: "harnesslab.turn",
      parent_span_id: null,
    });
    const step = span({
      span_id: "step1",
      name: "harnesslab.step",
      parent_span_id: "turn1",
    });
    const llm = span({
      span_id: "llm1",
      name: "llm.generate",
      parent_span_id: "step1",
    });
    const root = buildSpanTree([turn, step, llm]);
    expect(root?.span.name).toBe("harnesslab.turn");
    expect(root?.children[0]?.span.name).toBe("harnesslab.step");
    expect(root?.children[0]?.children[0]?.span.name).toBe("llm.generate");
  });
});

describe("groupSpansByTrace", () => {
  it("groups turns by trace_id", () => {
    const t0 = span({
      trace_id: "a",
      span_id: "turn0",
      name: "harnesslab.turn",
      turn_index: 0,
    });
    const t1 = span({
      trace_id: "b",
      span_id: "turn1",
      name: "harnesslab.turn",
      turn_index: 1,
    });
    const groups = groupSpansByTrace([t0, t1]);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.turnIndex)).toEqual([0, 1]);
  });
});

describe("buildSpanTree fallback", () => {
  it("builds tree when turn root span is missing from jsonl", () => {
    const step = span({
      span_id: "step1",
      name: "harnesslab.step",
      parent_span_id: "missing-turn",
      attributes: { "harnesslab.step.index": 0 },
    });
    const llm = span({
      span_id: "llm1",
      name: "llm.generate",
      parent_span_id: "step1",
    });
    const root = buildSpanTree([step, llm]);
    expect(root?.span.attributes?.["harnesslab.synthetic.turn_root"]).toBe(true);
    expect(root?.children[0]?.span.name).toBe("harnesslab.step");
    expect(root?.children[0]?.children[0]?.span.name).toBe("llm.generate");
  });
});

describe("filterFlatSpanRows", () => {
  it("filters by span name and attributes", () => {
    const turn = span({
      span_id: "turn1",
      name: "harnesslab.turn",
    });
    const tool = span({
      span_id: "tool1",
      name: "tool.read_file",
      parent_span_id: "turn1",
      attributes: { "harnesslab.tool.name": "read_file" },
    });
    const root = buildSpanTree([turn, tool])!;
    const flat = flattenSpanTree(root, new Set());
    expect(filterFlatSpanRows(flat, "read_file")).toHaveLength(1);
    expect(filterFlatSpanRows(flat, "harnesslab.tool.name")).toHaveLength(1);
    expect(filterFlatSpanRows(flat, "")).toHaveLength(flat.length);
  });
});
