import type { SpanRecordItem } from "./schemas";
import { spanDisplayLabel, spanDisplaySubtitle, spanOperationHint } from "./spanDisplay";

function flattenForSearch(value: unknown, depth = 0): string {
  if (value == null || depth > 4) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => flattenForSearch(item, depth + 1)).join(" ");
  }
  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>)
      .map((item) => flattenForSearch(item, depth + 1))
      .join(" ");
  }
  return "";
}

/** Deep search across span name, attributes, metrics (prompt blocks, tool I/O). */
export function spanMatchesDeepQuery(span: SpanRecordItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    span.name,
    span.span_id,
    span.trace_id,
    spanOperationHint(span) ?? "",
    spanDisplayLabel(span),
    spanDisplaySubtitle(span) ?? "",
    flattenForSearch(span.attributes),
    flattenForSearch(span.metrics),
    flattenForSearch(span.events),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}
