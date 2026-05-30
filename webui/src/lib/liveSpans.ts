import type { SpanRecordItem, SpanStartedPayload } from "./schemas";

const LIVE_ATTR = "harnesslab.live";

export function isLiveSpan(span: SpanRecordItem): boolean {
  return span.attributes?.[LIVE_ATTR] === true;
}

function startedToPlaceholder(payload: SpanStartedPayload, nowMs: number): SpanRecordItem {
  const now = new Date(nowMs).toISOString();
  return {
    trace_id: payload.trace_id,
    span_id: payload.span_id,
    parent_span_id: payload.parent_span_id ?? null,
    name: payload.name,
    kind: payload.kind,
    session_id: payload.session_id,
    turn_index: payload.turn_index ?? 0,
    start_time: now,
    end_time: now,
    duration_ms: 0,
    attributes: {
      ...(payload.attributes ?? {}),
      [LIVE_ATTR]: true,
    },
    child_session_id: payload.child_session_id,
  };
}

/** Merge disk + completed SSE + in-flight ``span.started`` placeholders. */
export function mergeTraceSpans(
  persisted: SpanRecordItem[],
  completed: SpanRecordItem[],
  started: SpanStartedPayload[],
  startMsBySpanId: Readonly<Record<string, number>> = {}
): SpanRecordItem[] {
  const byId = new Map<string, SpanRecordItem>();
  for (const span of persisted) byId.set(span.span_id, span);
  for (const span of completed) byId.set(span.span_id, span);

  for (const payload of started) {
    if (byId.has(payload.span_id)) continue;
    const startMs = startMsBySpanId[payload.span_id] ?? Date.now();
    byId.set(payload.span_id, startedToPlaceholder(payload, startMs));
  }

  return [...byId.values()].sort(
    (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
  );
}
