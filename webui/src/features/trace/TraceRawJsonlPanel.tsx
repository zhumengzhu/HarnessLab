import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../../lib/api-client";
import { copyText } from "../../lib/copyText";
import type { TraceEventItem, TraceJsonlResponse } from "../../lib/schemas";
import { filterTraceEvents, traceEventsToJsonl } from "../../lib/traceJsonl";
import { useI18n } from "../../lib/i18n";

type TraceRawJsonlPanelProps = {
  sessionId: string | null;
  liveRows: TraceEventItem[];
  loading: boolean;
  error: string | null;
  hasStreamTrace: boolean;
};

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "application/x-ndjson;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function TraceRawJsonlPanel(props: TraceRawJsonlPanelProps) {
  const { sessionId, liveRows, loading, error, hasStreamTrace } = props;
  const { t } = useI18n();
  const [filter, setFilter] = useState("");
  const [copied, setCopied] = useState(false);

  const persisted = useQuery({
    queryKey: ["trace-jsonl", sessionId],
    queryFn: () =>
      apiGet<TraceJsonlResponse>(
        `/api/sessions/${encodeURIComponent(sessionId || "")}/trace/jsonl`
      ),
    enabled: Boolean(sessionId),
  });

  const jsonl = useMemo(() => {
    if (hasStreamTrace && liveRows.length) {
      return traceEventsToJsonl(filterTraceEvents(liveRows, filter));
    }
    const disk = persisted.data?.jsonl ?? "";
    if (!filter.trim()) {
      return disk || traceEventsToJsonl(liveRows);
    }
    if (disk) {
      const filtered = disk
        .split("\n")
        .filter(Boolean)
        .filter((line) => line.toLowerCase().includes(filter.trim().toLowerCase()));
      return filtered.length ? `${filtered.join("\n")}\n` : "";
    }
    return traceEventsToJsonl(filterTraceEvents(liveRows, filter));
  }, [filter, hasStreamTrace, liveRows, persisted.data?.jsonl]);

  const lineCount = jsonl.trim() ? jsonl.trim().split("\n").length : 0;
  const tracePath = persisted.data?.trace_path ?? null;
  const isLoading = loading || persisted.isLoading;

  return (
    <section className="panel trace-jsonl-panel">
      <div className="panel-title-row">
        <div>
          <h2>{t("trace.jsonlTitle")}</h2>
          <p className="trace-jsonl-subtitle">{t("trace.jsonlHint")}</p>
        </div>
        <div className="trace-jsonl-actions">
          <button
            type="button"
            disabled={!jsonl.trim()}
            onClick={() => {
              void copyText(jsonl).then((ok) => {
                setCopied(ok);
                if (ok) window.setTimeout(() => setCopied(false), 2000);
              });
            }}
          >
            {copied ? t("trace.jsonlCopied") : t("trace.jsonlCopy")}
          </button>
          <button
            type="button"
            disabled={!jsonl.trim() || !sessionId}
            onClick={() =>
              downloadText(`${sessionId ?? "session"}-trace.jsonl`, jsonl)
            }
          >
            {t("trace.jsonlDownload")}
          </button>
        </div>
      </div>

      {!sessionId ? <p>{t("trace.selectSession")}</p> : null}
      {isLoading ? <p>{t("trace.loading")}</p> : null}
      {error ? <p className="error-text">{t("common.loadFailed", { error })}</p> : null}
      {persisted.isError ? (
        <p className="error-text">{t("common.loadFailed", { error: (persisted.error as Error).message })}</p>
      ) : null}

      {sessionId ? (
        <>
          <div className="trace-jsonl-meta">
            <span>
              {t("trace.jsonlLines", { count: String(lineCount) })}
              {hasStreamTrace ? ` · ${t("trace.jsonlLive")}` : ""}
            </span>
            {tracePath ? (
              <code className="trace-jsonl-path" title={tracePath}>
                {tracePath}
              </code>
            ) : null}
          </div>

          <label className="trace-jsonl-filter">
            <span>{t("trace.jsonlFilter")}</span>
            <input
              type="search"
              value={filter}
              placeholder={t("trace.jsonlFilterPlaceholder")}
              onChange={(e) => setFilter(e.target.value)}
            />
          </label>

          <pre className="trace-jsonl-pre">{jsonl || t("trace.jsonlEmpty")}</pre>
        </>
      ) : null}
    </section>
  );
}
