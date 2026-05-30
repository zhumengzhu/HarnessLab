import type { SpanEventPayload, SpanRecordItem, SpanStartedPayload } from "../../lib/schemas";

export type ActivityEntry = {
  id: string;
  kind: "tool" | "tool_denied" | "step" | "thinking" | "compact" | "steer" | "spawn" | "failover";
  label: string;
  detail?: string;
  ok?: boolean;
  at: string;
};

function previewText(raw: unknown, max = 96): string {
  const text = String(raw ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}

export function activityEntryFromSpanStarted(payload: SpanStartedPayload): ActivityEntry | null {
  if (payload.name === "harnesslab.step") {
    const stepIndex = payload.attributes?.["harnesslab.step.index"];
    return {
      id: `${payload.span_id}-step`,
      kind: "step",
      label: `step ${String(stepIndex ?? "?")} started`,
      at: new Date().toISOString(),
    };
  }
  if (payload.name === "llm.generate") {
    const stepIndex = payload.attributes?.["harnesslab.step.index"];
    const thinking = payload.attributes?.["harnesslab.thinking.enabled"];
    return {
      id: `${payload.span_id}-llm`,
      kind: "thinking",
      label: `step ${String(stepIndex ?? "?")} · ${thinking ? "thinking…" : "calling model"}`,
      at: new Date().toISOString(),
    };
  }
  if (payload.name === "sub_agent.run") {
    const goal = previewText(payload.attributes?.["harnesslab.sub_agent.goal"]);
    return {
      id: `${payload.span_id}-spawn`,
      kind: "spawn",
      label: "sub-agent spawn",
      detail: goal,
      at: new Date().toISOString(),
    };
  }
  return null;
}

export function activityEntryFromSpanCompleted(span: SpanRecordItem): ActivityEntry | null {
  if (span.name.startsWith("tool.") && !span.name.startsWith("tool.hooks.")) {
    const tool = String(span.attributes["harnesslab.tool.name"] ?? span.name.slice(5));
    const ok = Boolean(span.attributes["harnesslab.tool.ok"] ?? span.status !== "error");
    const duration =
      typeof span.metrics?.duration_ms === "number"
        ? ` · ${Math.round(span.metrics.duration_ms)}ms`
        : "";
    if (!ok && span.attributes["harnesslab.policy.decision"]) {
      return {
        id: `${span.span_id}-deny`,
        kind: "tool_denied",
        label: `${tool} · denied`,
        detail: previewText(span.metrics?.error ?? "policy denied"),
        ok: false,
        at: span.end_time,
      };
    }
    return {
      id: `${span.span_id}-tool`,
      kind: "tool",
      label: `${tool} · ${ok ? "ok" : "error"}${duration}`,
      detail: previewText(span.metrics?.output_preview ?? span.metrics?.error),
      ok,
      at: span.end_time,
    };
  }
  if (span.name === "context.compact") {
    const trigger = String(span.attributes["harnesslab.compaction.trigger"] ?? "compact");
    return {
      id: `${span.span_id}-compact`,
      kind: "compact",
      label: `compact · ${trigger}`,
      at: span.end_time,
    };
  }
  if (span.name === "llm.generate") {
    const attempts = span.attributes["harnesslab.failover.attempts"];
    if (typeof attempts === "number" && attempts > 1) {
      return {
        id: `${span.span_id}-failover`,
        kind: "failover",
        label: `failover · ${attempts} attempts`,
        at: span.end_time,
      };
    }
  }
  return null;
}

export function activityEntryFromSpanEvent(payload: SpanEventPayload): ActivityEntry | null {
  if (payload.name === "user.steer.received") {
    return {
      id: `${payload.span_id}-${payload.name}`,
      kind: "steer",
      label: "steer received",
      detail: previewText(payload.attributes?.user_input),
      at: new Date().toISOString(),
    };
  }
  return null;
}

export function buildActivityFeedFromSpans(
  spans: SpanRecordItem[],
  cap = 200
): ActivityEntry[] {
  const entries: ActivityEntry[] = [];
  for (const span of spans) {
    const completed = activityEntryFromSpanCompleted(span);
    if (completed) entries.push(completed);
    for (const evt of span.events ?? []) {
      const mapped = activityEntryFromSpanEvent({
        trace_id: span.trace_id,
        span_id: span.span_id,
        name: evt.name,
        attributes: evt.attributes,
      });
      if (mapped) entries.push({ ...mapped, at: evt.time || span.end_time });
    }
  }
  const sorted = entries.sort((a, b) => a.at.localeCompare(b.at));
  if (sorted.length <= cap) return sorted.reverse();
  return sorted.slice(sorted.length - cap).reverse();
}

export function buildActivityFeed(spans: SpanRecordItem[], cap = 200): ActivityEntry[] {
  return buildActivityFeedFromSpans(spans, cap);
}
