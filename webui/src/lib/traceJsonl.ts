import type { SpanRecordItem } from "./schemas";

export function spanToJsonLine(span: SpanRecordItem): string {
  return JSON.stringify(span);
}

export function spansToJsonl(spans: SpanRecordItem[]): string {
  if (!spans.length) return "";
  return `${spans.map(spanToJsonLine).join("\n")}\n`;
}

export function filterSpans(spans: SpanRecordItem[], query: string): SpanRecordItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return spans;
  return spans.filter((span) => {
    if (span.name.toLowerCase().includes(needle)) return true;
    const blob = JSON.stringify(span).toLowerCase();
    return blob.includes(needle);
  });
}
