export type SseHandlers = {
  onTrace?: (payload: unknown) => void;
  onReasoningDelta?: (payload: { text: string; step_index?: number }) => void;
  onAssistantDelta?: (payload: { text: string; step_index?: number }) => void;
  onDone?: (payload: unknown) => void;
  onError?: (message: string) => void;
};

export async function postSse(
  path: string,
  body: Record<string, unknown>,
  handlers: SseHandlers,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ ...body, stream: true }),
    signal,
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("SSE stream missing body");
  }
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    if (signal?.aborted) {
      await reader.cancel().catch(() => undefined);
      throw new DOMException("Aborted", "AbortError");
    }
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let eventType = "";
      let dataLine = "";
      for (const line of lines) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        if (line.startsWith("data:")) dataLine = line.slice(5).trim();
      }
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine);
      if (eventType === "trace" && handlers.onTrace) handlers.onTrace(payload);
      if (eventType === "reasoning_delta" && handlers.onReasoningDelta) {
        handlers.onReasoningDelta(payload as { text: string; step_index?: number });
      }
      if (eventType === "assistant_delta" && handlers.onAssistantDelta) {
        handlers.onAssistantDelta(payload as { text: string; step_index?: number });
      }
      if (eventType === "done" && handlers.onDone) handlers.onDone(payload);
      if (eventType === "error" && handlers.onError) {
        handlers.onError(String(payload?.message || "stream error"));
      }
    }
  }
}
