import type { SpanRecordItem } from "./schemas";

export type TurnLlmSummary = {
  llmCalls: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  costUsd: number | null;
  latencyMs: number;
};

export function aggregateTurnLlmMetrics(spans: SpanRecordItem[], traceId: string | null): TurnLlmSummary {
  const summary: TurnLlmSummary = {
    llmCalls: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    costUsd: null,
    latencyMs: 0,
  };
  for (const span of spans) {
    if (traceId && span.trace_id !== traceId) continue;
    if (span.name !== "llm.generate") continue;
    summary.llmCalls += 1;
    const metrics = span.metrics ?? {};
    summary.inputTokens += numberMetric(metrics.input_tokens);
    summary.outputTokens += numberMetric(metrics.output_tokens);
    summary.totalTokens += numberMetric(metrics.total_tokens);
    summary.latencyMs += numberMetric(metrics.latency_ms);
    const cost = metrics.cost_usd;
    if (typeof cost === "number" && Number.isFinite(cost)) {
      summary.costUsd = (summary.costUsd ?? 0) + cost;
    }
  }
  return summary;
}

export type LlmPromptSnapshot = {
  spanId: string;
  turnIndex: number;
  traceId: string;
  endTime: string;
  promptBlocks: unknown[];
  apiMessages: unknown[];
};

export function collectLlmPromptSnapshots(spans: SpanRecordItem[]): LlmPromptSnapshot[] {
  const rows: LlmPromptSnapshot[] = [];
  for (const span of spans) {
    if (span.name !== "llm.generate") continue;
    const metrics = span.metrics ?? {};
    rows.push({
      spanId: span.span_id,
      turnIndex: span.turn_index,
      traceId: span.trace_id,
      endTime: span.end_time,
      promptBlocks: Array.isArray(metrics.prompt_blocks) ? metrics.prompt_blocks : [],
      apiMessages: Array.isArray(metrics.api_messages) ? metrics.api_messages : [],
    });
  }
  return rows.sort((a, b) => a.endTime.localeCompare(b.endTime));
}

function numberMetric(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
