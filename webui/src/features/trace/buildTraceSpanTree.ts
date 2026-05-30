import type { TraceEventItem } from "../../lib/schemas";

export type TraceSpanStatus = "ok" | "error" | "warn" | "running" | "neutral";

export type TraceSpanKind =
  | "session"
  | "turn"
  | "step"
  | "model"
  | "tool"
  | "compaction"
  | "hook"
  | "budget"
  | "event";

export type TraceSpanNode = {
  id: string;
  kind: TraceSpanKind;
  name: string;
  status: TraceSpanStatus;
  startMs: number;
  durationMs: number | null;
  depth: number;
  children: TraceSpanNode[];
  eventType?: string;
  payload?: Record<string, unknown>;
  events: TraceEventItem[];
};

function parseTime(iso: string): number {
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : 0;
}

function previewText(raw: unknown, max = 48): string {
  const text = String(raw ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}

function childDepth(parent: TraceSpanNode): number {
  return parent.depth + 1;
}

function appendLeaf(parent: TraceSpanNode, node: TraceSpanNode): void {
  node.depth = childDepth(parent);
  parent.children.push(node);
}

function eventLeaf(
  parent: TraceSpanNode,
  evt: TraceEventItem,
  relMs: number,
  name: string,
  kind: TraceSpanKind = "event",
  status: TraceSpanStatus = "neutral"
): TraceSpanNode {
  const node: TraceSpanNode = {
    id: `${evt.event_type}-${evt.created_at}`,
    kind,
    name,
    status,
    startMs: relMs,
    durationMs: null,
    depth: 0,
    eventType: evt.event_type,
    payload: evt.payload,
    events: [evt],
    children: [],
  };
  appendLeaf(parent, node);
  return node;
}

function toolStatus(eventType: string, payload: Record<string, unknown>): TraceSpanStatus {
  if (eventType === "tool_denied" || eventType === "tool_invalid_args") {
    return "error";
  }
  if (eventType === "tool_executed") {
    return payload.ok === false ? "error" : "ok";
  }
  return "neutral";
}

function toolName(eventType: string, payload: Record<string, unknown>): string {
  const tool = String(payload.tool || "tool");
  if (eventType === "tool_denied") return `${tool} · denied`;
  if (eventType === "tool_invalid_args") return `${tool} · invalid args`;
  return `${tool} · ${payload.ok === false ? "error" : "ok"}`;
}

function stepOutcomeStatus(outcome: unknown): TraceSpanStatus {
  const text = String(outcome ?? "");
  if (/denied|error|invalid|fail/i.test(text)) return "error";
  return "ok";
}

/** Flatten tree for list rendering (depth-first). */
export function flattenTraceSpanTree(root: TraceSpanNode): TraceSpanNode[] {
  const rows: TraceSpanNode[] = [];
  const walk = (node: TraceSpanNode) => {
    rows.push(node);
    for (const child of node.children) {
      walk(child);
    }
  };
  walk(root);
  return rows;
}

/** Build a Jaeger-style span hierarchy from flat HarnessLab trace events. */
export function buildTraceSpanTree(events: TraceEventItem[]): TraceSpanNode | null {
  if (!events.length) return null;

  const sorted = [...events].sort((a, b) => {
    const delta = parseTime(a.created_at) - parseTime(b.created_at);
    if (delta !== 0) return delta;
    return a.event_type.localeCompare(b.event_type);
  });

  const t0 = parseTime(sorted[0].created_at);
  const rel = (iso: string) => Math.max(0, parseTime(iso) - t0);

  const root: TraceSpanNode = {
    id: "session-root",
    kind: "session",
    name: "session",
    status: "neutral",
    startMs: 0,
    durationMs: null,
    depth: 0,
    children: [],
    events: [],
  };

  let currentTurn: TraceSpanNode | null = null;
  let currentStep: TraceSpanNode | null = null;
  let openModel: TraceSpanNode | null = null;
  let openCompaction: TraceSpanNode | null = null;

  const activeParent = (): TraceSpanNode => currentStep ?? currentTurn ?? root;

  for (const evt of sorted) {
    const et = evt.event_type;
    const payload = evt.payload;

    if (et === "session_started") {
      root.name = previewText(payload.goal, 64) || "session";
      root.events.push(evt);
      continue;
    }

    if (et === "user_input_received") {
      currentStep = null;
      openModel = null;
      const turnIndex =
        typeof payload.turn_index === "number" ? payload.turn_index : root.children.length;
      currentTurn = {
        id: `turn-${turnIndex}-${evt.created_at}`,
        kind: "turn",
        name: `turn ${turnIndex} · ${previewText(payload.user_input) || "user input"}`,
        status: "neutral",
        startMs: rel(evt.created_at),
        durationMs: null,
        depth: 1,
        children: [],
        eventType: et,
        payload,
        events: [evt],
      };
      root.children.push(currentTurn);
      continue;
    }

    if (et === "step_started") {
      openModel = null;
      const stepIndex = payload.step_index;
      currentStep = {
        id: `step-${stepIndex}-${evt.created_at}`,
        kind: "step",
        name: typeof stepIndex === "number" ? `step ${stepIndex}` : "step",
        status: "running",
        startMs: rel(evt.created_at),
        durationMs: null,
        depth: 0,
        children: [],
        eventType: et,
        payload,
        events: [evt],
      };
      appendLeaf(currentTurn ?? root, currentStep);
      continue;
    }

    if (et === "step_completed") {
      if (currentStep) {
        currentStep.durationMs = Math.max(0, rel(evt.created_at) - currentStep.startMs);
        currentStep.status = stepOutcomeStatus(payload.outcome);
        currentStep.events.push(evt);
        if (typeof payload.outcome === "string" && payload.outcome) {
          currentStep.name = `${currentStep.name} · ${payload.outcome}`;
        }
      }
      openModel = null;
      continue;
    }

    if (et === "model_call_started") {
      openModel = {
        id: `model-${evt.created_at}`,
        kind: "model",
        name: "model call",
        status: "running",
        startMs: rel(evt.created_at),
        durationMs: null,
        depth: 0,
        children: [],
        eventType: et,
        payload,
        events: [evt],
      };
      appendLeaf(activeParent(), openModel);
      continue;
    }

    if (et === "model_call") {
      const latency =
        typeof payload.latency_ms === "number"
          ? payload.latency_ms
          : openModel
            ? Math.max(0, rel(evt.created_at) - openModel.startMs)
            : null;
      const decision = typeof payload.decision_kind === "string" ? payload.decision_kind : "call";
      const failoverAttempts =
        typeof payload.failover_attempts === "number" ? payload.failover_attempts : 0;

      if (openModel) {
        openModel.durationMs = latency;
        openModel.status =
          failoverAttempts > 1 ? "warn" : payload.failover_exhausted ? "error" : "ok";
        openModel.name = `model · ${decision}`;
        openModel.payload = payload;
        openModel.eventType = "model_call";
        openModel.events.push(evt);
        openModel = null;
      } else {
        eventLeaf(
          activeParent(),
          evt,
          rel(evt.created_at),
          `model · ${decision}`,
          "model",
          failoverAttempts > 1 ? "warn" : "ok"
        ).durationMs = latency;
      }
      continue;
    }

    if (et === "tool_executed" || et === "tool_denied" || et === "tool_invalid_args") {
      const durationMs =
        typeof payload.duration_ms === "number" ? payload.duration_ms : null;
      const span: TraceSpanNode = {
        id: `${et}-${evt.created_at}`,
        kind: "tool",
        name: toolName(et, payload),
        status: toolStatus(et, payload),
        startMs:
          durationMs != null ? Math.max(0, rel(evt.created_at) - durationMs) : rel(evt.created_at),
        durationMs,
        depth: 0,
        children: [],
        eventType: et,
        payload,
        events: [evt],
      };
      appendLeaf(activeParent(), span);
      continue;
    }

    if (et === "compaction_started") {
      openCompaction = {
        id: `compact-${evt.created_at}`,
        kind: "compaction",
        name: "compaction",
        status: "running",
        startMs: rel(evt.created_at),
        durationMs: null,
        depth: 0,
        children: [],
        eventType: et,
        payload,
        events: [evt],
      };
      appendLeaf(root, openCompaction);
      continue;
    }

    if (et === "compaction_completed") {
      if (openCompaction) {
        openCompaction.durationMs = Math.max(0, rel(evt.created_at) - openCompaction.startMs);
        openCompaction.status = "ok";
        openCompaction.events.push(evt);
        if (typeof payload.messages_after === "number") {
          openCompaction.name = `compaction · ${payload.messages_after} msgs`;
        }
        openCompaction = null;
      } else {
        eventLeaf(root, evt, rel(evt.created_at), "compaction completed", "compaction", "ok");
      }
      continue;
    }

    if (et === "hook_invoked" || et === "hook_blocked" || et === "hook_failed") {
      const hookName = String(payload.name || payload.hook || "hook");
      eventLeaf(
        activeParent(),
        evt,
        rel(evt.created_at),
        `${hookName} · ${et.replace("hook_", "")}`,
        "hook",
        et === "hook_blocked" || et === "hook_failed" ? "error" : "neutral"
      );
      continue;
    }

    if (
      et === "budget_soft_threshold" ||
      et === "budget_hard_exceeded" ||
      et === "budget_enforcement_action"
    ) {
      eventLeaf(
        root,
        evt,
        rel(evt.created_at),
        et.replace("budget_", "budget · "),
        "budget",
        et.includes("hard") ? "error" : "warn"
      );
      continue;
    }

    if (et === "decision_made") {
      const kind = String(payload.kind || "decision");
      eventLeaf(activeParent(), evt, rel(evt.created_at), `decision · ${kind}`, "event", "neutral");
      continue;
    }

    if (et === "sub_agent_spawned" || et === "sub_agent_completed") {
      eventLeaf(
        activeParent(),
        evt,
        rel(evt.created_at),
        et === "sub_agent_spawned" ? "sub-agent spawned" : "sub-agent completed",
        "event",
        "neutral"
      );
      continue;
    }

    if (et === "session_finished" || et === "session_titled") {
      eventLeaf(root, evt, rel(evt.created_at), et.replace(/_/g, " "), "event", "neutral");
      continue;
    }

    eventLeaf(activeParent(), evt, rel(evt.created_at), et.replace(/_/g, " "), "event", "neutral");
  }

  const last = sorted[sorted.length - 1];
  root.durationMs = Math.max(0, rel(last.created_at));

  for (const turn of root.children) {
    if (turn.kind === "turn" && turn.durationMs == null) {
      const turnEnd = turn.children.length
        ? Math.max(...flattenTraceSpanTree(turn).map((n) => (n.startMs ?? 0) + (n.durationMs ?? 0)))
        : turn.startMs;
      turn.durationMs = Math.max(0, turnEnd - turn.startMs);
    }
  }

  return root;
}

export function formatSpanDuration(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}
