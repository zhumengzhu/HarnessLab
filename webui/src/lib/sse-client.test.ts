import { describe, expect, it, vi } from "vitest";
import { postSse } from "./sse-client";

function sseChunk(event: string, data: unknown): Uint8Array {
  const body = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  return new TextEncoder().encode(body);
}

function mockSseResponse(chunks: Uint8Array[]): Response {
  let index = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(chunks[index++]);
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("postSse event ordering", () => {
  it("delivers span lifecycle, deltas, then done in order", async () => {
    const order: string[] = [];
    const fetchMock = vi.fn(async () =>
      mockSseResponse([
        sseChunk("span.started", {
          trace_id: "t1",
          span_id: "s1",
          name: "harnesslab.step",
          session_id: "ses_1",
        }),
        sseChunk("span.completed", {
          trace_id: "t1",
          span_id: "s1",
          name: "harnesslab.step",
          session_id: "ses_1",
          turn_index: 0,
          start_time: "2026-05-30T12:00:00Z",
          end_time: "2026-05-30T12:00:01Z",
          duration_ms: 1000,
          attributes: {},
        }),
        sseChunk("reasoning_delta", { text: "think ", step_index: 0 }),
        sseChunk("assistant_delta", { text: "Hi", step_index: 0 }),
        sseChunk("done", { session_id: "ses_1", response: "Hi" }),
      ])
    );
    vi.stubGlobal("fetch", fetchMock);

    await postSse(
      "/api/sessions/ses_1/messages",
      { content: "hello" },
      {
        onSpanStarted: () => order.push("span.started"),
        onSpanCompleted: () => order.push("span.completed"),
        onReasoningDelta: () => order.push("reasoning_delta"),
        onAssistantDelta: () => order.push("assistant_delta"),
        onDone: () => order.push("done"),
      }
    );

    expect(order).toEqual([
      "span.started",
      "span.completed",
      "reasoning_delta",
      "assistant_delta",
      "done",
    ]);

    vi.unstubAllGlobals();
  });

  it("surfaces error events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockSseResponse([sseChunk("error", { message: "boom" })]))
    );

    let message = "";
    await postSse("/api/sessions/ses_1/messages", { content: "x" }, {
      onError: (m) => {
        message = m;
      },
    });

    expect(message).toBe("boom");
    vi.unstubAllGlobals();
  });
});
