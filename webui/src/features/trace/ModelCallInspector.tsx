import type { TraceEventItem } from "../../lib/schemas";

type PromptBlock = {
  name: string;
  role: string;
  origin: string;
  content: string;
  char_count?: number;
};

type ModelCallInspectorProps = {
  payload: Record<string, unknown>;
};

export function ModelCallInspector({ payload }: ModelCallInspectorProps) {
  const blocks = Array.isArray(payload.prompt_blocks)
    ? (payload.prompt_blocks as PromptBlock[])
    : [];
  const apiMessages = Array.isArray(payload.api_messages) ? payload.api_messages : [];
  const reasoning =
    typeof payload.reasoning_text === "string" ? payload.reasoning_text : null;
  const latencyMs =
    typeof payload.latency_ms === "number" ? payload.latency_ms : null;

  if (!blocks.length && !apiMessages.length && !reasoning) {
    return null;
  }

  return (
    <div className="trace-model-call-inspector">
      {latencyMs != null ? (
        <div className="trace-inspector-meta">
          latency: {latencyMs.toFixed(0)}ms
          {typeof payload.decision_kind === "string" ? ` · ${payload.decision_kind}` : ""}
        </div>
      ) : null}

      {reasoning ? (
        <details className="trace-inspector-section">
          <summary>Reasoning ({reasoning.length} chars)</summary>
          <pre>{reasoning}</pre>
        </details>
      ) : null}

      {blocks.length > 0 ? (
        <details className="trace-inspector-section" open>
          <summary>Prompt blocks ({blocks.length})</summary>
          <div className="trace-prompt-blocks">
            {blocks.map((block) => (
              <details key={`${block.name}-${block.origin}`} className="trace-prompt-block">
                <summary>
                  {block.name} · {block.role} · {block.char_count ?? block.content.length} chars
                  <span className="trace-prompt-origin">{block.origin}</span>
                </summary>
                <pre>{block.content}</pre>
              </details>
            ))}
          </div>
        </details>
      ) : null}

      {apiMessages.length > 0 ? (
        <details className="trace-inspector-section">
          <summary>API messages ({apiMessages.length})</summary>
          <pre>{JSON.stringify(apiMessages, null, 2)}</pre>
        </details>
      ) : null}
    </div>
  );
}

export function summarizeModelCall(payload: Record<string, unknown>): string {
  const latency =
    typeof payload.latency_ms === "number" ? `${payload.latency_ms.toFixed(0)}ms` : "";
  const kind = typeof payload.decision_kind === "string" ? payload.decision_kind : "";
  const blocks = Array.isArray(payload.prompt_blocks) ? payload.prompt_blocks.length : 0;
  const reasoning =
    typeof payload.reasoning_text === "string" ? payload.reasoning_text.length : 0;
  const parts = [kind, latency].filter(Boolean);
  if (blocks) parts.push(`${blocks} blocks`);
  if (reasoning) parts.push(`reasoning ${reasoning}c`);
  return parts.join(" · ") || "model call";
}

export function isModelCallEvent(evt: TraceEventItem): boolean {
  return evt.event_type === "model_call" || evt.event_type === "model_call_started";
}
