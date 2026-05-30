import type { TraceSpanNode } from "./buildTraceSpanTree";
import { formatSpanDuration } from "./buildTraceSpanTree";
import { useI18n } from "../../lib/i18n";
import { ModelCallInspector } from "./ModelCallInspector";

type TraceSpanDetailProps = {
  span: TraceSpanNode | null;
  sessionDurationMs: number | null;
};

function fieldRows(payload: Record<string, unknown>): Array<[string, string]> {
  const skip = new Set(["prompt_blocks", "api_messages", "context", "reasoning_text"]);
  const rows: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(payload)) {
    if (skip.has(key)) continue;
    if (value == null) continue;
    if (typeof value === "object") {
      rows.push([key, JSON.stringify(value)]);
    } else {
      rows.push([key, String(value)]);
    }
  }
  return rows;
}

export function TraceSpanDetail({ span, sessionDurationMs }: TraceSpanDetailProps) {
  const { t } = useI18n();
  if (!span) {
    return (
      <div className="trace-span-detail trace-span-detail-empty">
        <p>{t("trace.selectSpan")}</p>
      </div>
    );
  }

  const payload = span.payload ?? {};
  const barDenominator = sessionDurationMs && sessionDurationMs > 0 ? sessionDurationMs : null;

  return (
    <div className="trace-span-detail">
      <header className="trace-span-detail-header">
        <h3>{span.name}</h3>
        <div className="trace-span-detail-meta">
          <span className={`trace-span-status trace-span-status-${span.status}`}>{span.status}</span>
          <span>{formatSpanDuration(span.durationMs)}</span>
          {span.eventType ? <span>{span.eventType}</span> : null}
        </div>
      </header>

      {barDenominator != null && span.durationMs != null ? (
        <div className="trace-span-detail-bar" aria-hidden>
          <div
            className="trace-span-detail-bar-fill"
            style={{
              marginLeft: `${Math.min(100, (span.startMs / barDenominator) * 100)}%`,
              width: `${Math.max(0.5, (span.durationMs / barDenominator) * 100)}%`,
            }}
          />
        </div>
      ) : null}

      {Object.keys(payload).length ? (
        <dl className="trace-span-fields">
          {fieldRows(payload).map(([key, value]) => (
            <div key={key} className="trace-span-field">
              <dt>{key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {span.kind === "model" && typeof payload.decision_kind === "string" ? (
        <ModelCallInspector payload={payload} />
      ) : null}

      {span.events.length ? (
        <details className="trace-inspector-section">
          <summary>{t("trace.sourceEvents", { count: span.events.length })}</summary>
          <ul className="trace-span-source-events">
            {span.events.map((evt) => (
              <li key={`${evt.event_type}-${evt.created_at}`}>
                <strong>{evt.event_type}</strong>
                <span>{evt.created_at}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <details className="trace-raw-json">
        <summary>{t("trace.rawJson")}</summary>
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </details>
    </div>
  );
}
