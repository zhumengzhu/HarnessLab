import type { SpanRecordItem } from "./schemas";

const DEFAULT_SERVICE = "harnesslab";

/** OTel ``service.name`` from span resource (Jaeger Process.serviceName). */
export function spanServiceName(span: SpanRecordItem): string {
  const name = span.resource?.["service.name"];
  if (typeof name === "string" && name.trim()) return name.trim();
  return DEFAULT_SERVICE;
}

/** Resource / Process tags for the detail panel (sorted key/value rows). */
export function spanResourceRows(span: SpanRecordItem): Array<[string, string]> {
  const resource = span.resource ?? {};
  const rows: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(resource)) {
    if (value == null) continue;
    rows.push([key, formatResourceValue(value)]);
  }
  if (!rows.length) {
    rows.push(["service.name", spanServiceName(span)]);
  }
  rows.sort((a, b) => a[0].localeCompare(b[0]));
  return rows;
}

function formatResourceValue(value: unknown): string {
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
