import type { MessageItem, ToolCard, TraceEventItem } from "./schemas";
import { toolCardFromTraceEvent } from "./toolCardFromTrace";
import type { ThoughtEntry } from "../features/live-turn/liveTurnReducer";
import {
  mergeMessageReasoningIntoThoughts,
  thoughtsWithText,
} from "./thoughtUtils";

export type TurnEnrichment = {
  thoughts: ThoughtEntry[];
  tools: ToolCard[];
};

export function findTerminalAssistantMessage(
  messages: MessageItem[]
): MessageItem | null {
  const visible = messages.filter(
    (m) =>
      m.role === "assistant" && (m.content.trim().length > 0 || Boolean(m.reasoning_text))
  );
  return visible.length ? visible[visible.length - 1] : null;
}

export function enrichmentFromLiveTurn(
  thoughts: ThoughtEntry[],
  tools: ToolCard[],
  doneTools?: ToolCard[],
  fallbackReasoning?: string
): TurnEnrichment {
  let finalizedThoughts = thoughts
    .filter((t) => t.status === "done" || t.text)
    .map((t) =>
      t.status === "thinking"
        ? {
            ...t,
            status: "done" as const,
            durationMs: Math.max(0, Date.now() - t.startedAt),
          }
        : t
    );
  if (fallbackReasoning?.trim()) {
    finalizedThoughts = mergeMessageReasoningIntoThoughts(
      finalizedThoughts,
      fallbackReasoning,
      new Date().toISOString()
    );
  }
  return {
    thoughts: thoughtsWithText(finalizedThoughts),
    tools: doneTools?.length ? doneTools : tools,
  };
}

function splitMessageTurns(messages: MessageItem[]): MessageItem[][] {
  const turns: MessageItem[][] = [];
  let current: MessageItem[] = [];
  for (const msg of messages) {
    if (msg.role === "user" && current.length > 0) {
      turns.push(current);
      current = [msg];
    } else {
      current.push(msg);
    }
  }
  if (current.length) turns.push(current);
  return turns;
}

function terminalAssistantInTurn(turnMessages: MessageItem[]): MessageItem | null {
  const assistants = turnMessages.filter((m) => m.role === "assistant");
  const visible = assistants.filter(
    (m) => m.content.trim().length > 0 || Boolean(m.reasoning_text)
  );
  return visible.length ? visible[visible.length - 1] : assistants[assistants.length - 1] ?? null;
}

function traceEventsForTurn(
  events: TraceEventItem[],
  turnIndex: number
): TraceEventItem[] {
  const rows: TraceEventItem[] = [];
  let capturing = false;
  for (const evt of events) {
    if (evt.event_type === "user_input_received") {
      const idx = evt.payload.turn_index;
      if (typeof idx === "number" && idx === turnIndex) {
        capturing = true;
        rows.length = 0;
        continue;
      }
      if (capturing) break;
    }
    if (capturing) rows.push(evt);
  }
  return rows;
}

function thoughtsFromTraceEvents(events: TraceEventItem[]): ThoughtEntry[] {
  // Reasoning is owned by model_call (+ SSE reasoning_delta during live turns).
  // decision_made repeats the same reasoning_text and must not be merged here.
  let thoughts: ThoughtEntry[] = [];
  let stepIndex = 0;
  for (const evt of events) {
    if (evt.event_type === "model_call_started") {
      const idx =
        typeof evt.payload.step_index === "number" ? evt.payload.step_index : stepIndex;
      stepIndex = idx;
      thoughts.push({
        stepIndex: idx,
        status: "thinking",
        startedAt: new Date(evt.created_at).getTime(),
      });
      continue;
    }
    if (evt.event_type === "model_call") {
      const latencyMs =
        typeof evt.payload.latency_ms === "number" ? evt.payload.latency_ms : undefined;
      const reasoning =
        typeof evt.payload.reasoning_text === "string" ? evt.payload.reasoning_text : undefined;
      const idx =
        typeof evt.payload.step_index === "number" ? evt.payload.step_index : stepIndex;
      const existing = thoughts.find(
        (t) => t.stepIndex === idx && t.status === "thinking"
      );
      if (existing) {
        existing.status = "done";
        existing.text = reasoning ?? existing.text;
        existing.durationMs = latencyMs;
      } else if (reasoning || latencyMs != null) {
        thoughts.push({
          stepIndex: idx,
          status: "done",
          text: reasoning,
          startedAt: new Date(evt.created_at).getTime() - (latencyMs ?? 0),
          durationMs: latencyMs,
        });
      }
      continue;
    }
  }
  return thoughtsWithText(
    thoughts.map((t) => ({ ...t, status: "done" as const }))
  );
}

function toolsFromTraceEvents(events: TraceEventItem[]): ToolCard[] {
  const tools: ToolCard[] = [];
  for (const evt of events) {
    if (evt.event_type === "tool_executed") {
      const card = toolCardFromTraceEvent(evt);
      if (card) tools.push(card);
    }
    if (evt.event_type === "tool_denied") {
      tools.push({
        tool: String(evt.payload.tool || "tool"),
        ok: false,
        error: String(evt.payload.reason || evt.payload.policy_decision || "denied"),
        output_preview: "",
        output_truncated: false,
        duration_ms: null,
      });
    }
  }
  return tools;
}

/** Map terminal assistant message id → thoughts + tools for each user turn. */
export function buildTurnEnrichmentsFromTrace(
  messages: MessageItem[],
  traceEvents: TraceEventItem[]
): Record<string, TurnEnrichment> {
  const turns = splitMessageTurns(messages);
  const out: Record<string, TurnEnrichment> = {};

  turns.forEach((turnMessages, turnIndex) => {
    const target = terminalAssistantInTurn(turnMessages);
    if (!target) return;

    const turnTrace = traceEventsForTurn(traceEvents, turnIndex);
    let thoughts = thoughtsFromTraceEvents(turnTrace);
    thoughts = mergeMessageReasoningIntoThoughts(
      thoughts,
      target.reasoning_text,
      target.created_at
    );
    const tools = toolsFromTraceEvents(turnTrace);

    if (!thoughts.length && !tools.length) return;
    out[target.id] = { thoughts, tools };
  });

  return out;
}

export function mergeTurnEnrichments(
  ...maps: Array<Record<string, TurnEnrichment>>
): Record<string, TurnEnrichment> {
  const out: Record<string, TurnEnrichment> = {};
  for (const map of maps) {
    for (const [id, enrichment] of Object.entries(map)) {
      out[id] = enrichment;
    }
  }
  return out;
}
