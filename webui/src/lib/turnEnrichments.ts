import type { MessageItem, SpanRecordItem, ToolCard } from "./schemas";
import { toolCardFromSpan } from "./toolCardFromSpan";
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

function spansForTurn(spans: SpanRecordItem[], turnIndex: number): SpanRecordItem[] {
  const turnRoots = spans.filter(
    (span) => span.name === "harnesslab.turn" && span.turn_index === turnIndex
  );
  if (!turnRoots.length) return [];
  const traceIds = new Set(turnRoots.map((span) => span.trace_id));
  return spans.filter((span) => traceIds.has(span.trace_id));
}

function thoughtsFromSpans(spans: SpanRecordItem[]): ThoughtEntry[] {
  const thoughts: ThoughtEntry[] = [];
  for (const span of spans) {
    if (span.name !== "llm.generate") continue;
    const stepIndex =
      typeof span.attributes["harnesslab.step.index"] === "number"
        ? (span.attributes["harnesslab.step.index"] as number)
        : 0;
    const latencyMs =
      typeof span.metrics?.latency_ms === "number" ? span.metrics.latency_ms : undefined;
    const reasoning =
      typeof span.metrics?.reasoning_text === "string" ? span.metrics.reasoning_text : undefined;
    thoughts.push({
      stepIndex,
      status: "done",
      text: reasoning,
      startedAt: new Date(span.start_time).getTime(),
      durationMs: latencyMs,
    });
  }
  return thoughtsWithText(thoughts);
}

function toolsFromSpans(spans: SpanRecordItem[]): ToolCard[] {
  const tools: ToolCard[] = [];
  for (const span of spans) {
    const card = toolCardFromSpan(span);
    if (card) tools.push(card);
  }
  return tools;
}

/** Map terminal assistant message id → thoughts + tools for each user turn. */
export function buildTurnEnrichmentsFromSpans(
  messages: MessageItem[],
  spans: SpanRecordItem[]
): Record<string, TurnEnrichment> {
  const turns = splitMessageTurns(messages);
  const out: Record<string, TurnEnrichment> = {};

  turns.forEach((turnMessages, turnIndex) => {
    const target = terminalAssistantInTurn(turnMessages);
    if (!target) return;

    const turnSpans = spansForTurn(spans, turnIndex);
    let thoughts = thoughtsFromSpans(turnSpans);
    thoughts = mergeMessageReasoningIntoThoughts(
      thoughts,
      target.reasoning_text,
      target.created_at
    );
    const tools = toolsFromSpans(turnSpans);

    if (!thoughts.length && !tools.length) return;
    out[target.id] = { thoughts, tools };
  });

  return out;
}

/** @deprecated use buildTurnEnrichmentsFromSpans */
export function buildTurnEnrichmentsFromTrace(
  messages: MessageItem[],
  _traceEvents: unknown[]
): Record<string, TurnEnrichment> {
  return buildTurnEnrichmentsFromSpans(messages, []);
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
