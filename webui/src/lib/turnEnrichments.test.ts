import { describe, expect, it } from "vitest";
import {
  buildTurnEnrichmentsFromSpans,
  enrichmentFromLiveTurn,
  findTerminalAssistantMessage,
} from "./turnEnrichments";
import type { MessageItem, SpanRecordItem } from "./schemas";

function msg(partial: Partial<MessageItem> & Pick<MessageItem, "id" | "role" | "content">): MessageItem {
  return {
    created_at: "2026-05-25T00:00:00.000Z",
    ...partial,
  };
}

function span(partial: Partial<SpanRecordItem> & Pick<SpanRecordItem, "span_id" | "name">): SpanRecordItem {
  return {
    trace_id: "t1",
    session_id: "s1",
    turn_index: 0,
    start_time: "2026-05-25T00:00:01.000Z",
    end_time: "2026-05-25T00:00:02.000Z",
    duration_ms: 1000,
    attributes: {},
    ...partial,
  };
}

describe("turnEnrichments", () => {
  it("finds terminal assistant with content", () => {
    const messages = [
      msg({ id: "u1", role: "user", content: "hi" }),
      msg({ id: "a1", role: "assistant", content: "" }),
      msg({ id: "a2", role: "assistant", content: "done" }),
    ];
    expect(findTerminalAssistantMessage(messages)?.id).toBe("a2");
  });

  it("archives live turn thoughts and tools", () => {
    const enrichment = enrichmentFromLiveTurn(
      [
        {
          stepIndex: 0,
          status: "done",
          text: "reasoning",
          startedAt: Date.now() - 1000,
          durationMs: 1000,
        },
      ],
      [{ tool: "read_file", ok: true, output_preview: "x" }]
    );
    expect(enrichment.thoughts).toHaveLength(1);
    expect(enrichment.tools).toHaveLength(1);
  });

  it("builds enrichments from spans per turn", () => {
    const messages = [
      msg({ id: "u1", role: "user", content: "run" }),
      msg({ id: "a1", role: "assistant", content: "final answer" }),
    ];
    const spans = [
      span({ span_id: "turn0", name: "harnesslab.turn", turn_index: 0 }),
      span({
        span_id: "llm0",
        name: "llm.generate",
        parent_span_id: "turn0",
        metrics: { latency_ms: 800, reasoning_text: "think first" },
        attributes: { "harnesslab.step.index": 0 },
      }),
      span({
        span_id: "tool0",
        name: "tool.grep",
        parent_span_id: "turn0",
        attributes: { "harnesslab.tool.name": "grep", "harnesslab.tool.ok": true },
        metrics: { output_preview: "matches", duration_ms: 12 },
      }),
    ];
    const map = buildTurnEnrichmentsFromSpans(messages, spans);
    expect(map.a1?.thoughts[0].text).toBe("think first");
    expect(map.a1?.tools[0].tool).toBe("grep");
  });
});
