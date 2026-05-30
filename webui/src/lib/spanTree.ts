import type { SpanRecordItem } from "./schemas";
import { isLiveSpan } from "./liveSpans";

/** Jaeger-style span tree node built from native ``parent_span_id``. */
export type SpanTreeNode = {
  span: SpanRecordItem;
  children: SpanTreeNode[];
  depth: number;
};

export type SpanTraceGroup = {
  traceId: string;
  turnIndex: number;
  root: SpanTreeNode;
  traceStartMs: number;
  traceDurationMs: number;
};

export type FlatSpanRow = {
  node: SpanTreeNode;
  collapsed: boolean;
  hasChildren: boolean;
};

const SPAN_TURN = "harnesslab.turn";

function parseTime(iso: string): number {
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : 0;
}

export function formatSpanDuration(durationMs: number | null | undefined): string {
  if (durationMs == null || !Number.isFinite(durationMs)) return "…";
  if (durationMs < 1) return "<1ms";
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  return `${(durationMs / 1000).toFixed(2)}s`;
}

export function spanStatus(span: SpanRecordItem): "ok" | "error" | "warn" | "running" | "neutral" {
  if (isLiveSpan(span)) return "running";
  if (span.status === "error") return "error";
  if (span.name.startsWith("tool.") && span.attributes["harnesslab.tool.ok"] === false) {
    return "error";
  }
  if (span.status === "ok") return "ok";
  return "neutral";
}

/** Build one trace tree from completed spans sharing a ``trace_id``. */
export function buildSpanTree(spans: SpanRecordItem[]): SpanTreeNode | null {
  if (!spans.length) return null;

  const strictRoot = findStrictRoot(spans);
  if (strictRoot) {
    return attachSpanTree(strictRoot, spans, 0);
  }

  return buildSpanTreeFromParentLinks(spans);
}

function findStrictRoot(spans: SpanRecordItem[]): SpanRecordItem | null {
  let roots = spans.filter((span) => span.parent_span_id == null);
  if (roots.length !== 1) {
    roots = spans.filter((span) => span.name === SPAN_TURN && span.parent_span_id == null);
  }
  return roots.length === 1 ? roots[0] : null;
}

function attachSpanTree(
  rootSpan: SpanRecordItem,
  spans: SpanRecordItem[],
  depth: number
): SpanTreeNode {
  const childMap = new Map<string | null, SpanRecordItem[]>();
  for (const span of spans) {
    const parentId = span.parent_span_id ?? null;
    const bucket = childMap.get(parentId) ?? [];
    bucket.push(span);
    childMap.set(parentId, bucket);
  }

  function attach(span: SpanRecordItem, nodeDepth: number): SpanTreeNode {
    const children = (childMap.get(span.span_id) ?? []).map((child) => attach(child, nodeDepth + 1));
    return { span, children, depth: nodeDepth };
  }

  return attach(rootSpan, depth);
}

/** Fallback when ``harnesslab.turn`` was not persisted (open turn / crash). */
function buildSpanTreeFromParentLinks(spans: SpanRecordItem[]): SpanTreeNode | null {
  if (!spans.length) return null;

  const byId = new Map(spans.map((span) => [span.span_id, span]));
  const childMap = new Map<string, SpanRecordItem[]>();
  const topLevel: SpanRecordItem[] = [];

  for (const span of spans) {
    const parentId = span.parent_span_id;
    if (parentId && byId.has(parentId)) {
      const bucket = childMap.get(parentId) ?? [];
      bucket.push(span);
      childMap.set(parentId, bucket);
    } else {
      topLevel.push(span);
    }
  }

  const turnSpan = spans.find((span) => span.name === SPAN_TURN);
  if (turnSpan) {
    return attachLinkedTree(turnSpan, childMap, 0);
  }

  const starts = spans.map((span) => parseTime(span.start_time));
  const ends = spans.map((span) => parseTime(span.end_time));
  const traceStartMs = Math.min(...starts);
  const traceEndMs = Math.max(...ends);
  const syntheticRoot: SpanRecordItem = {
    trace_id: spans[0].trace_id,
    span_id: `synthetic-root-${spans[0].trace_id}`,
    parent_span_id: null,
    name: SPAN_TURN,
    session_id: spans[0].session_id,
    turn_index: spans[0].turn_index ?? 0,
    start_time: new Date(traceStartMs).toISOString(),
    end_time: new Date(traceEndMs).toISOString(),
    duration_ms: Math.max(1, traceEndMs - traceStartMs),
    status: "ok",
    attributes: { "harnesslab.synthetic.turn_root": true },
  };

  return {
    span: syntheticRoot,
    depth: 0,
    children: topLevel.map((span) => attachLinkedTree(span, childMap, 1)),
  };
}

function attachLinkedTree(
  span: SpanRecordItem,
  childMap: Map<string, SpanRecordItem[]>,
  depth: number
): SpanTreeNode {
  const children = (childMap.get(span.span_id) ?? []).map((child) =>
    attachLinkedTree(child, childMap, depth + 1)
  );
  return { span, children, depth };
}

/** Group session spans into per-turn traces (Jaeger: one trace = one request). */
export function groupSpansByTrace(spans: SpanRecordItem[]): SpanTraceGroup[] {
  const byTrace = new Map<string, SpanRecordItem[]>();
  for (const span of spans) {
    const bucket = byTrace.get(span.trace_id) ?? [];
    bucket.push(span);
    byTrace.set(span.trace_id, bucket);
  }

  const groups: SpanTraceGroup[] = [];
  for (const [traceId, traceSpans] of byTrace.entries()) {
    const root = buildSpanTree(traceSpans);
    if (!root) continue;
    const turnIndex =
      typeof root.span.turn_index === "number"
        ? root.span.turn_index
        : Number(root.span.attributes["harnesslab.turn.index"] ?? 0);
    const starts = traceSpans.map((span) => parseTime(span.start_time));
    const ends = traceSpans.map((span) =>
      isLiveSpan(span) ? Date.now() : parseTime(span.end_time)
    );
    const traceStartMs = Math.min(...starts);
    const traceEndMs = Math.max(...ends);
    groups.push({
      traceId,
      turnIndex,
      root,
      traceStartMs,
      traceDurationMs: Math.max(1, traceEndMs - traceStartMs),
    });
  }

  groups.sort((a, b) => a.turnIndex - b.turnIndex || a.traceStartMs - b.traceStartMs);
  return groups;
}

export function flattenSpanTree(
  root: SpanTreeNode,
  collapsedIds: ReadonlySet<string>
): FlatSpanRow[] {
  const rows: FlatSpanRow[] = [];

  function walk(node: SpanTreeNode) {
    const hasChildren = node.children.length > 0;
    const collapsed = collapsedIds.has(node.span.span_id);
    rows.push({ node, collapsed, hasChildren });
    if (!collapsed) {
      for (const child of node.children) {
        walk(child);
      }
    }
  }

  walk(root);
  return rows;
}

export function spanTimeline(
  span: SpanRecordItem,
  traceStartMs: number,
  traceDurationMs: number
): { offsetPct: number; widthPct: number } {
  const startMs = parseTime(span.start_time) - traceStartMs;
  const endMs = isLiveSpan(span)
    ? Date.now()
    : parseTime(span.end_time);
  const durationMs =
    span.duration_ms && !isLiveSpan(span)
      ? span.duration_ms
      : Math.max(0, endMs - parseTime(span.start_time));
  const denom = traceDurationMs > 0 ? traceDurationMs : 1;
  return {
    offsetPct: Math.min(100, Math.max(0, (startMs / denom) * 100)),
    widthPct: Math.max(0.5, Math.min(100, (durationMs / denom) * 100)),
  };
}

/** Collect span ids that have children (for expand/collapse all). */
export function collectCollapsibleSpanIds(root: SpanTreeNode): string[] {
  const ids: string[] = [];
  function walk(node: SpanTreeNode) {
    if (node.children.length) {
      ids.push(node.span.span_id);
      for (const child of node.children) {
        walk(child);
      }
    }
  }
  walk(root);
  return ids;
}

export function filterFlatSpanRows(rows: FlatSpanRow[], query: string): FlatSpanRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter(({ node }) => {
    const name = node.span.name.toLowerCase();
    if (name.includes(q)) return true;
    const attrs = node.span.attributes ?? {};
    return Object.entries(attrs).some(([key, value]) => {
      const hay = `${key} ${String(value ?? "")}`.toLowerCase();
      return hay.includes(q);
    });
  });
}

/** Ruler tick marks for the waterfall header (Jaeger-style). */
export function buildTimelineTicks(
  traceDurationMs: number,
  tickCount = 4
): Array<{ label: string; pct: number }> {
  const ticks: Array<{ label: string; pct: number }> = [{ label: "0", pct: 0 }];
  if (traceDurationMs <= 0) return ticks;
  for (let i = 1; i <= tickCount; i++) {
    const pct = (i / tickCount) * 100;
    const ms = (traceDurationMs * i) / tickCount;
    ticks.push({ label: formatSpanDuration(ms), pct });
  }
  return ticks;
}

export function formatRelativeStart(
  span: SpanRecordItem,
  traceStartMs: number
): string {
  const startMs = parseTime(span.start_time) - traceStartMs;
  if (startMs <= 0) return "+0ms";
  return `+${formatSpanDuration(startMs)}`;
}
