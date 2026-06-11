import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../../lib/api-client";
import { copyText } from "../../lib/copyText";
import type { SpanRecordItem, TraceJsonlResponse } from "../../lib/schemas";
import { filterSpans, spansToJsonl } from "../../lib/traceJsonl";
import { downloadTraceHtml } from "../../lib/traceHtmlExport";
import { useI18n } from "../../lib/i18n";

function jsonlToSpans(jsonl: string): SpanRecordItem[] {
  const rows: SpanRecordItem[] = [];
  for (const line of jsonl.split("\n")) {
    if (!line.trim()) continue;
    try {
      rows.push(JSON.parse(line) as SpanRecordItem);
    } catch {
      // skip malformed lines
    }
  }
  return rows;
}

type TraceRawJsonlPanelProps = {
  sessionId: string | null;
  liveSpans: SpanRecordItem[];
  loading: boolean;
  error: string | null;
  hasStreamSpans: boolean;
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
  const { sessionId, liveSpans, loading, error, hasStreamSpans } = props;
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
    if (hasStreamSpans && liveSpans.length) {
      return spansToJsonl(filterSpans(liveSpans, filter));
    }
    const disk = persisted.data?.jsonl ?? "";
    if (!filter.trim()) {
      return disk || spansToJsonl(liveSpans);
    }
    if (disk) {
      const filtered = disk
        .split("\n")
        .filter(Boolean)
        .filter((line) => line.toLowerCase().includes(filter.trim().toLowerCase()));
      return filtered.length ? `${filtered.join("\n")}\n` : "";
    }
    return spansToJsonl(filterSpans(liveSpans, filter));
  }, [filter, hasStreamSpans, liveSpans, persisted.data?.jsonl]);

  const exportSpans = useMemo(() => {
    if (hasStreamSpans && liveSpans.length) {
      return filterSpans(liveSpans, filter);
    }
    return jsonlToSpans(jsonl);
  }, [filter, hasStreamSpans, jsonl, liveSpans]);

  const lineCount = jsonl.trim() ? jsonl.trim().split("\n").length : 0;
  const spansPath = persisted.data?.spans_path ?? persisted.data?.trace_path ?? null;
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
              downloadText(`${sessionId ?? "session"}-spans.jsonl`, jsonl)
            }
          >
            {t("trace.jsonlDownload")}
          </button>
          <button
            type="button"
            disabled={!exportSpans.length || !sessionId}
            onClick={() => downloadTraceHtml(sessionId ?? "session", exportSpans)}
          >
            {t("trace.htmlDownload")}
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
              {hasStreamSpans ? ` · ${t("trace.jsonlLive")}` : ""}
            </span>
            {spansPath ? (
              <code className="trace-jsonl-path" title={spansPath}>
                {spansPath}
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
