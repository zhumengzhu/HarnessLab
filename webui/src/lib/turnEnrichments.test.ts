import { describe, expect, it } from "vitest";
import {
  buildTurnEnrichmentsFromTrace,
  enrichmentFromLiveTurn,
  findTerminalAssistantMessage,
} from "./turnEnrichments";
import type { MessageItem, TraceEventItem } from "./schemas";

function msg(partial: Partial<MessageItem> & Pick<MessageItem, "id" | "role" | "content">): MessageItem {
  return {
    created_at: "2026-05-25T00:00:00.000Z",
    ...partial,
  };
}

function trace(
  event_type: string,
  payload: Record<string, unknown>,
  created_at = "2026-05-25T00:00:01.000Z"
): TraceEventItem {
  return {
    run_id: "r1",
    session_id: "s1",
    event_type,
    payload,
    created_at,
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

  it("builds enrichments from trace per turn", () => {
    const messages = [
      msg({ id: "u1", role: "user", content: "run" }),
      msg({ id: "a1", role: "assistant", content: "final answer" }),
    ];
    const events = [
      trace("user_input_received", { turn_index: 0, user_input: "run" }, "2026-05-25T00:00:00.000Z"),
      trace("model_call", {
        latency_ms: 800,
        reasoning_text: "think first",
      }),
      trace("tool_executed", {
        tool: "grep",
        ok: true,
        output_preview: "matches",
        duration_ms: 12,
      }),
    ];
    const map = buildTurnEnrichmentsFromTrace(messages, events);
    expect(map.a1?.thoughts[0].text).toBe("think first");
    expect(map.a1?.tools[0].tool).toBe("grep");
  });

  it("ignores duplicate reasoning on decision_made after model_call", () => {
    const messages = [
      msg({ id: "u1", role: "user", content: "run" }),
      msg({ id: "a1", role: "assistant", content: "final answer" }),
    ];
    const reasoning = "Let me search for MIMO pricing context.";
    const events = [
      trace("user_input_received", { turn_index: 0, user_input: "run" }, "2026-05-25T00:00:00.000Z"),
      trace("model_call_started", { step_index: 0 }),
      trace("model_call", {
        step_index: 0,
        latency_ms: 3500,
        reasoning_text: reasoning,
      }),
      trace("decision_made", {
        step_index: 0,
        kind: "tool",
        reasoning_text: reasoning,
      }),
    ];
    const map = buildTurnEnrichmentsFromTrace(messages, events);
    expect(map.a1?.thoughts).toHaveLength(1);
    expect(map.a1?.thoughts[0].durationMs).toBe(3500);
    expect(map.a1?.thoughts[0].text).toBe(reasoning);
  });
});
