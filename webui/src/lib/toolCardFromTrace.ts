import type { ToolCard, TraceEventItem } from "./schemas";

export function toolCardFromTraceEvent(evt: TraceEventItem): ToolCard | null {
  if (evt.event_type !== "tool_executed") return null;
  const payload = evt.payload;
  return {
    tool: String(payload.tool || "tool"),
    ok: Boolean(payload.ok ?? true),
    error: payload.error != null ? String(payload.error) : null,
    output_preview:
      payload.output_preview != null ? String(payload.output_preview) : "",
    output_truncated: Boolean(payload.output_truncated ?? false),
    duration_ms:
      typeof payload.duration_ms === "number" ? payload.duration_ms : null,
  };
}
