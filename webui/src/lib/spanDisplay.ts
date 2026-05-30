import type { SpanRecordItem } from "./schemas";

export type SpanDisplayKind =
  | "turn"
  | "step"
  | "llm"
  | "tool"
  | "compact"
  | "sub_agent"
  | "skill"
  | "other";

export function spanDisplayKind(name: string): SpanDisplayKind {
  if (name === "harnesslab.turn") return "turn";
  if (name === "harnesslab.step") return "step";
  if (name === "llm.generate" || name === "llm.title") return "llm";
  if (name === "context.compact") return "compact";
  if (name === "sub_agent.run") return "sub_agent";
  if (name.startsWith("skill.")) return "skill";
  if (name.startsWith("tool.")) return "tool";
  return "other";
}

function stepIndex(span: SpanRecordItem): number | null {
  const raw = span.attributes?.["harnesslab.step.index"];
  return typeof raw === "number" ? raw : null;
}

function turnIndex(span: SpanRecordItem): number {
  if (typeof span.turn_index === "number") return span.turn_index;
  const raw = span.attributes?.["harnesslab.turn.index"];
  return typeof raw === "number" ? raw : 0;
}

/** Canonical operation name for trace UI (``domain.action``, Jaeger ``operationName``). */
export function spanOperationName(span: SpanRecordItem): string {
  return span.name;
}

/** Optional attribute hint beside operation name in the waterfall (index, model, denial reason). */
export function spanOperationHint(span: SpanRecordItem): string | null {
  const attrs = span.attributes ?? {};
  if (span.name === "harnesslab.step") {
    const idx = stepIndex(span);
    return idx == null ? null : `index=${idx}`;
  }
  if (span.name === "harnesslab.turn") {
    const reason = attrs["harnesslab.terminal.reason"];
    if (typeof reason === "string" && reason) return reason;
    return `index=${turnIndex(span)}`;
  }
  if (span.name.startsWith("tool.") && !span.name.startsWith("tool.hooks.")) {
    if (attrs["harnesslab.policy.decision"]) {
      return String(attrs["harnesslab.policy.reason"] ?? "policy denied");
    }
  }
  if (span.name === "llm.generate") {
    const model = attrs["gen_ai.request.model"];
    if (typeof model === "string" && model) return model;
    const decision = attrs["harnesslab.decision.kind"];
    if (typeof decision === "string" && decision) return decision;
  }
  if (span.name === "sub_agent.run") {
    const goal = attrs["harnesslab.sub_agent.goal"];
    return typeof goal === "string" && goal ? goal.slice(0, 40) : null;
  }
  return null;
}

/** Friendly label for chat / activity (not the trace waterfall). */
export function spanDisplayLabel(span: SpanRecordItem): string {
  const name = span.name;
  if (name === "harnesslab.turn") {
    if (span.attributes?.["harnesslab.synthetic.turn_root"]) {
      return `Turn ${turnIndex(span)} · incomplete trace`;
    }
    return `Turn ${turnIndex(span)}`;
  }
  if (name === "harnesslab.step") {
    const idx = stepIndex(span);
    return idx == null ? "Step" : `Step ${idx}`;
  }
  if (name === "llm.generate") return "LLM";
  if (name === "llm.title") return "Session title";
  if (name === "context.compact") return "Compact context";
  if (name === "sub_agent.run") {
    const goal = span.attributes?.["harnesslab.sub_agent.goal"];
    return typeof goal === "string" && goal ? `Sub-agent · ${goal.slice(0, 48)}` : "Sub-agent";
  }
  if (name.startsWith("tool.")) {
    const tool = span.attributes?.["harnesslab.tool.name"];
    return typeof tool === "string" && tool ? tool : name.slice(5);
  }
  if (name.startsWith("skill.")) return name.slice(6);
  return name;
}

export function spanDisplaySubtitle(span: SpanRecordItem): string | null {
  const attrs = span.attributes ?? {};
  if (span.name === "llm.generate") {
    const parts: string[] = [];
    const decision = attrs["harnesslab.decision.kind"];
    if (typeof decision === "string" && decision) parts.push(decision);
    if (attrs["harnesslab.thinking.enabled"]) parts.push("thinking");
    const model = attrs["gen_ai.request.model"];
    if (typeof model === "string" && model) parts.push(model);
    return parts.length ? parts.join(" · ") : null;
  }
  if (span.name.startsWith("tool.") && !span.name.startsWith("tool.hooks.")) {
    if (attrs["harnesslab.policy.decision"]) {
      return String(attrs["harnesslab.policy.reason"] ?? "policy denied");
    }
    const ok = attrs["harnesslab.tool.ok"];
    return ok === false ? "failed" : "ok";
  }
  if (span.name === "harnesslab.turn") {
    const reason = attrs["harnesslab.terminal.reason"];
    return typeof reason === "string" && reason ? reason : null;
  }
  if (span.name === "context.compact") {
    const trigger = attrs["harnesslab.compaction.trigger"];
    return typeof trigger === "string" ? trigger : null;
  }
  return null;
}

export function spanMatchesQuery(span: SpanRecordItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    span.name,
    spanOperationHint(span) ?? "",
    spanDisplayLabel(span),
    spanDisplaySubtitle(span) ?? "",
    span.span_id,
    span.trace_id,
    ...Object.entries(span.attributes ?? {}).flatMap(([k, v]) => [k, String(v ?? "")]),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}
