import type { TraceEventItem } from "./schemas";

/** One JSONL line matching ``JsonlTraceRecorder`` on disk. */
export function traceEventToJsonLine(event: TraceEventItem): string {
  return JSON.stringify({
    run_id: event.run_id,
    session_id: event.session_id,
    event_type: event.event_type,
    payload: event.payload,
    created_at: event.created_at,
  });
}

export function traceEventsToJsonl(events: TraceEventItem[]): string {
  if (!events.length) return "";
  return `${events.map(traceEventToJsonLine).join("\n")}\n`;
}

export function filterTraceEvents(
  events: TraceEventItem[],
  query: string
): TraceEventItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return events;
  return events.filter((event) => {
    if (event.event_type.toLowerCase().includes(needle)) return true;
    const payload = JSON.stringify(event.payload).toLowerCase();
    return payload.includes(needle);
  });
}
