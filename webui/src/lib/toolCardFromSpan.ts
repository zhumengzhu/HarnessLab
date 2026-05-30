import type { SpanRecordItem, ToolCard } from "./schemas";

export function toolCardFromSpan(span: SpanRecordItem): ToolCard | null {
  if (!span.name.startsWith("tool.") || span.name.startsWith("tool.hooks.")) {
    return null;
  }
  if (span.name.split(".").length !== 2) return null;
  const attrs = span.attributes ?? {};
  const metrics = span.metrics ?? {};
  const outputPreview =
    typeof metrics.output_preview === "string" ? metrics.output_preview : "";
  return {
    tool: String(attrs["harnesslab.tool.name"] ?? span.name.slice("tool.".length)),
    ok: Boolean(attrs["harnesslab.tool.ok"] ?? span.status !== "error"),
    error: typeof metrics.error === "string" ? metrics.error : null,
    output_preview: outputPreview,
    output_truncated: Boolean(metrics.output_truncated),
    duration_ms:
      typeof metrics.duration_ms === "number" ? metrics.duration_ms : span.duration_ms,
  };
}
