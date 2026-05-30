import type { TraceEventItem } from "../../lib/schemas";

export type ActivityEntry = {
  id: string;
  kind: "tool" | "tool_denied" | "step" | "thinking" | "compact" | "steer" | "spawn";
  label: string;
  detail?: string;
  ok?: boolean;
  at: string;
};

const ACTIVITY_EVENT_TYPES = new Set([
  "step_started",
  "model_call_started",
  "tool_executed",
  "tool_denied",
  "compaction_started",
  "compaction_completed",
  "user_steer_received",
  "sub_agent_spawned",
  "sub_agent_completed",
]);

export function isActivityTraceEvent(eventType: string): boolean {
  return ACTIVITY_EVENT_TYPES.has(eventType);
}

function previewText(raw: unknown, max = 96): string {
  const text = String(raw ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}

function argFieldCount(args: unknown): number | null {
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    return null;
  }
  return Object.keys(args as Record<string, unknown>).length;
}

export function activityEntryFromTrace(evt: TraceEventItem): ActivityEntry | null {
  if (!isActivityTraceEvent(evt.event_type)) {
    return null;
  }

  const payload = evt.payload;
  const id = `${evt.created_at}-${evt.event_type}-${String(payload.tool ?? payload.step_index ?? "")}`;

  if (evt.event_type === "tool_executed") {
    const tool = String(payload.tool || "tool");
    const ok = Boolean(payload.ok ?? true);
    const duration =
      typeof payload.duration_ms === "number" ? ` · ${Math.round(payload.duration_ms)}ms` : "";
    const argCount = argFieldCount(payload.args);
    const argLabel = argCount != null ? `${argCount} args` : "args hidden";
    const output = previewText(payload.output_preview);
    const detailParts = [argLabel];
    if (output) {
      detailParts.push(output);
    } else if (payload.error) {
      detailParts.push(previewText(payload.error));
    }
    return {
      id,
      kind: "tool",
      label: `${tool} · ${ok ? "ok" : "error"}${duration}`,
      detail: detailParts.join(" · "),
      ok,
      at: evt.created_at,
    };
  }

  if (evt.event_type === "tool_denied") {
    const tool = String(payload.tool || "tool");
    return {
      id,
      kind: "tool_denied",
      label: `${tool} · denied`,
      detail: previewText(payload.reason || "policy denied"),
      ok: false,
      at: evt.created_at,
    };
  }

  if (evt.event_type === "model_call_started") {
    const step =
      typeof payload.step_index === "number" ? `step ${payload.step_index}` : "model call";
    const thinking = payload.thinking_likely ? "thinking…" : "calling model";
    return {
      id,
      kind: "thinking",
      label: `${step} · ${thinking}`,
      at: evt.created_at,
    };
  }

  if (evt.event_type === "step_started") {
    const step =
      typeof payload.step_index === "number" ? `step ${payload.step_index}` : "agent step";
    return {
      id,
      kind: "step",
      label: step,
      at: evt.created_at,
    };
  }

  if (evt.event_type === "user_steer_received") {
    return {
      id,
      kind: "steer",
      label: "steer injected",
      detail: previewText(payload.user_input),
      at: evt.created_at,
    };
  }

  if (evt.event_type === "sub_agent_spawned") {
    const childId = String(payload.child_session_id || "");
    return {
      id,
      kind: "spawn",
      label: "sub-agent spawned",
      detail: previewText(payload.goal) || childId,
      at: evt.created_at,
    };
  }

  if (evt.event_type === "sub_agent_completed") {
    const childId = String(payload.child_session_id || "");
    return {
      id,
      kind: "spawn",
      label: "sub-agent finished",
      detail: previewText(payload.final_response_preview) || childId,
      at: evt.created_at,
    };
  }

  if (evt.event_type === "compaction_started") {
    return {
      id,
      kind: "compact",
      label: "compaction started",
      detail: previewText(payload.trigger),
      at: evt.created_at,
    };
  }

  return {
    id,
    kind: "compact",
    label: "compaction completed",
    detail:
      typeof payload.messages_after === "number"
        ? `${payload.messages_after} messages remain`
        : undefined,
    ok: true,
    at: evt.created_at,
  };
}

export function buildActivityFeed(events: TraceEventItem[], max = 40): ActivityEntry[] {
  const entries: ActivityEntry[] = [];
  const seen = new Set<string>();

  for (const evt of events) {
    const entry = activityEntryFromTrace(evt);
    if (!entry || seen.has(entry.id)) {
      continue;
    }
    seen.add(entry.id);
    entries.push(entry);
  }

  return entries.slice(-max).reverse();
}
