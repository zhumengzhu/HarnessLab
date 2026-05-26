import type { TraceEventItem } from "../../lib/schemas";
import {
  ModelCallInspector,
  isModelCallEvent,
  summarizeModelCall,
} from "./ModelCallInspector";

type TracePanelProps = {
  selectedSessionId: string | null;
  loading: boolean;
  error: string | null;
  rows: TraceEventItem[];
  hasStreamTrace: boolean;
  onClearStreamTrace: () => void;
};

export function TracePanel(props: TracePanelProps) {
  const {
    selectedSessionId,
    loading,
    error,
    rows,
    hasStreamTrace,
    onClearStreamTrace,
  } = props;
  return (
    <aside className="panel">
      <div className="panel-title-row">
        <h2>Trace</h2>
        <button type="button" onClick={onClearStreamTrace} disabled={!hasStreamTrace}>
          清空实时流
        </button>
      </div>
      {!selectedSessionId ? <p>Select a session.</p> : null}
      {loading ? <p>Loading trace...</p> : null}
      {error ? <p>Failed: {error}</p> : null}
      <ul className="trace-list">
        {!rows.length ? <li>暂无事件</li> : null}
        {rows.map((e, idx) => (
          <li key={`${e.created_at}-${e.event_type}-${idx}`}>
            <strong>{e.event_type}</strong>
            <div className="trace-summary">{summarizeTraceEvent(e.event_type, e.payload)}</div>
            {e.event_type === "model_call" ? (
              <ModelCallInspector payload={e.payload} />
            ) : null}
            {!isModelCallEvent(e) || e.event_type === "model_call_started" ? (
              <pre>{JSON.stringify(e.payload, null, 2)}</pre>
            ) : (
              <details className="trace-raw-json">
                <summary>Raw JSON</summary>
                <pre>{JSON.stringify(e.payload, null, 2)}</pre>
              </details>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}

function summarizeTraceEvent(eventType: string, payload: Record<string, unknown>): string {
  if (eventType === "model_call") {
    return summarizeModelCall(payload);
  }
  if (eventType === "model_call_started") {
    const step = payload.step_index;
    const thinking = payload.thinking_likely ? "thinking likely" : "call started";
    return typeof step === "number" ? `step ${step} · ${thinking}` : thinking;
  }
  if (eventType === "tool_executed") {
    const tool = String(payload.tool || "tool");
    const ok = Boolean(payload.ok);
    return `${tool} · ${ok ? "ok" : "error"}`;
  }
  if (eventType === "tool_denied") {
    return `denied · ${String(payload.reason || "unknown")}`;
  }
  if (eventType === "hook_blocked") {
    return `blocked by hook · ${String(payload.name || "")}`;
  }
  if (eventType === "budget_hard_exceeded") {
    return `budget hard · ${String(payload.dimension || "")}`;
  }
  if (eventType === "budget_soft_threshold") {
    return `budget soft · ${String(payload.dimension || "")}`;
  }
  if (eventType === "plan_emitted") {
    return "plan emitted";
  }
  if (eventType === "plan_recheck_requested") {
    return `recheck step=${String(payload.steps_used || "")}`;
  }
  return "event";
}
