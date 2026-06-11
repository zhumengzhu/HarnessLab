import type { SpanRecordItem } from "./schemas";
import { aggregateTurnLlmMetrics } from "./traceMetrics";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function traceBounds(spans: SpanRecordItem[]): { startMs: number; endMs: number } {
  let startMs = Number.POSITIVE_INFINITY;
  let endMs = 0;
  for (const span of spans) {
    const start = Date.parse(span.start_time);
    const end = Date.parse(span.end_time);
    if (Number.isFinite(start)) startMs = Math.min(startMs, start);
    if (Number.isFinite(end)) endMs = Math.max(endMs, end);
  }
  if (!Number.isFinite(startMs)) startMs = 0;
  return { startMs, endMs };
}

function spanDurationMs(span: SpanRecordItem): number {
  const start = Date.parse(span.start_time);
  const end = Date.parse(span.end_time);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 0;
  return Math.max(0, end - start);
}

function renderSpan(span: SpanRecordItem, traceStartMs: number): string {
  const relStart = Date.parse(span.start_time) - traceStartMs;
  const duration = spanDurationMs(span);
  const status = span.status ?? "OK";
  const attrs = Object.entries(span.attributes ?? {})
    .map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td><pre>${escapeHtml(String(value))}</pre></td></tr>`)
    .join("");
  const metrics = span.metrics ?? {};
  const metricKeys = Object.keys(metrics).filter((key) => key !== "context");
  const metricsHtml = metricKeys.length
    ? `<pre>${escapeHtml(JSON.stringify(metrics, null, 2))}</pre>`
    : "<p class=\"muted\">(none)</p>";

  return `<details class="span">
    <summary>
      <span class="name">${escapeHtml(span.name)}</span>
      <span class="meta">+${formatDurationMs(relStart)} · ${formatDurationMs(duration)} · ${escapeHtml(status)}</span>
    </summary>
    <div class="span-body">
      <dl class="ids">
        <dt>span_id</dt><dd><code>${escapeHtml(span.span_id)}</code></dd>
        <dt>trace_id</dt><dd><code>${escapeHtml(span.trace_id)}</code></dd>
        <dt>turn</dt><dd>${span.turn_index}</dd>
      </dl>
      ${attrs ? `<table class="attrs">${attrs}</table>` : ""}
      <h4>metrics</h4>
      ${metricsHtml}
    </div>
  </details>`;
}

/** Build a self-contained HTML trace report (no external assets). */
export function buildTraceHtml(
  spans: SpanRecordItem[],
  sessionId: string,
  exportedAt = new Date().toISOString()
): string {
  const sorted = [...spans].sort((a, b) => a.start_time.localeCompare(b.start_time));
  const byTrace = new Map<string, SpanRecordItem[]>();
  for (const span of sorted) {
    const list = byTrace.get(span.trace_id) ?? [];
    list.push(span);
    byTrace.set(span.trace_id, list);
  }

  const traceSections = [...byTrace.entries()]
    .map(([traceId, traceSpans]) => {
      const { startMs, endMs } = traceBounds(traceSpans);
      const duration = endMs - startMs;
      const turnIndex = traceSpans[0]?.turn_index ?? 0;
      const llm = aggregateTurnLlmMetrics(traceSpans, traceId);
      const body = traceSpans.map((span) => renderSpan(span, startMs)).join("\n");
      return `<section class="trace">
        <h2>Turn ${turnIndex} · <code>${escapeHtml(traceId.slice(0, 12))}…</code></h2>
        <p class="trace-summary">
          ${traceSpans.length} spans · ${formatDurationMs(duration)} ·
          ${llm.llmCalls} llm · ${llm.inputTokens}/${llm.outputTokens} tok
        </p>
        ${body}
      </section>`;
    })
    .join("\n");

  const embedded = JSON.stringify(sorted).replace(/</g, "\\u003c");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HarnessLab trace · ${escapeHtml(sessionId)}</title>
  <style>
    :root { color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; padding: 1.5rem; line-height: 1.45; max-width: 960px; }
    h1 { font-size: 1.25rem; margin: 0 0 0.5rem; }
    .header-meta { color: #666; font-size: 0.875rem; margin-bottom: 1.5rem; }
    .trace { margin-bottom: 2rem; border-top: 1px solid #ccc; padding-top: 1rem; }
    .trace-summary { color: #666; font-size: 0.875rem; }
    details.span { border: 1px solid #ddd; border-radius: 6px; margin: 0.5rem 0; }
    details.span summary { cursor: pointer; padding: 0.5rem 0.75rem; list-style: none; display: flex; gap: 1rem; flex-wrap: wrap; }
    details.span summary::-webkit-details-marker { display: none; }
    .name { font-weight: 600; }
    .meta { color: #666; font-size: 0.8125rem; }
    .span-body { padding: 0 0.75rem 0.75rem; }
    .ids { display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 1rem; font-size: 0.8125rem; }
    table.attrs { width: 100%; border-collapse: collapse; font-size: 0.8125rem; margin: 0.5rem 0; }
    table.attrs th { text-align: left; vertical-align: top; padding: 0.25rem 0.5rem 0.25rem 0; white-space: nowrap; }
    table.attrs td pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
    pre { background: rgba(127,127,127,0.08); padding: 0.5rem; border-radius: 4px; overflow: auto; font-size: 0.75rem; }
    .muted { color: #888; font-size: 0.875rem; }
    #search { width: 100%; max-width: 28rem; padding: 0.4rem 0.6rem; margin-bottom: 1rem; }
  </style>
</head>
<body>
  <h1>HarnessLab trace export</h1>
  <p class="header-meta">session <code>${escapeHtml(sessionId)}</code> · ${escapeHtml(exportedAt)} · ${sorted.length} spans</p>
  <input id="search" type="search" placeholder="Filter span name or attribute…" />
  <div id="traces">${traceSections || "<p>No spans.</p>"}</div>
  <script>
    const SPANS = ${embedded};
    const input = document.getElementById("search");
    const root = document.getElementById("traces");
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      for (const el of root.querySelectorAll("details.span")) {
        if (!q) { el.hidden = false; continue; }
        el.hidden = !el.textContent.toLowerCase().includes(q);
      }
    });
  </script>
</body>
</html>`;
}

export function downloadTraceHtml(sessionId: string, spans: SpanRecordItem[]): void {
  const html = buildTraceHtml(spans, sessionId);
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${sessionId}-trace.html`;
  anchor.click();
  URL.revokeObjectURL(url);
}
