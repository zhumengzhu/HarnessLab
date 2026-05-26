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
  it("delivers trace, deltas, then done in order", async () => {
    const order: string[] = [];
    const fetchMock = vi.fn(async () =>
      mockSseResponse([
        sseChunk("trace", { event_type: "model_call", step_index: 0 }),
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
        onTrace: () => order.push("trace"),
        onReasoningDelta: () => order.push("reasoning_delta"),
        onAssistantDelta: () => order.push("assistant_delta"),
        onDone: () => order.push("done"),
      }
    );

    expect(order).toEqual(["trace", "reasoning_delta", "assistant_delta", "done"]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sessions/ses_1/messages",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"stream":true'),
      })
    );

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
