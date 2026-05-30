import type { SpanRecordItem } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { ModelCallInspector } from "./ModelCallInspector";

type TracePanelProps = {
  selectedSessionId: string | null;
  loading: boolean;
  error: string | null;
  spans: SpanRecordItem[];
  hasStreamSpans: boolean;
  onClearStreamSpans: () => void;
};

export function TracePanel(props: TracePanelProps) {
  const {
    selectedSessionId,
    loading,
    error,
    spans,
    hasStreamSpans,
    onClearStreamSpans,
  } = props;
  const { t } = useI18n();
  return (
    <aside className="panel">
      <div className="panel-title-row">
        <h2>{t("trace.eventsTitle")}</h2>
        <button type="button" onClick={onClearStreamSpans} disabled={!hasStreamSpans}>
          {t("trace.clearStream")}
        </button>
      </div>
      {!selectedSessionId ? <p>{t("trace.selectSession")}</p> : null}
      {loading ? <p>{t("trace.loading")}</p> : null}
      {error ? <p>{t("common.loadFailed", { error })}</p> : null}
      <ul className="trace-list">
        {!spans.length ? <li>{t("trace.noEvents")}</li> : null}
        {spans.map((span) => (
          <li key={span.span_id}>
            <strong>{span.name}</strong>
            <div className="trace-summary">
              {span.status ?? "ok"} · {Math.round(span.duration_ms)}ms · turn {span.turn_index}
            </div>
            {span.name === "llm.generate" ? (
              <ModelCallInspector
                payload={{
                  ...(span.metrics ?? {}),
                  decision_kind: span.attributes["harnesslab.decision.kind"],
                }}
              />
            ) : null}
            <details className="trace-raw-json">
              <summary>{t("trace.rawJson")}</summary>
              <pre>{JSON.stringify(span, null, 2)}</pre>
            </details>
          </li>
        ))}
      </ul>
    </aside>
  );
}
