import { useState } from "react";
import { useI18n } from "../../lib/i18n";
import { CheckpointPanel } from "./CheckpointPanel";
import { TracePanel } from "../trace/TracePanel";
import { TraceSpanPanel } from "../trace/TraceSpanPanel";
import { TraceRawJsonlPanel } from "../trace/TraceRawJsonlPanel";
import type { TraceEventItem } from "../../lib/schemas";

export type TraceViewMode = "spans" | "events" | "jsonl";

type SessionTraceViewProps = {
  sessionId: string | null;
  loading: boolean;
  error: string | null;
  rows: TraceEventItem[];
  hasStreamTrace: boolean;
  onClearStreamTrace: () => void;
  onRewindSuccess: () => void;
};

export function SessionTraceView(props: SessionTraceViewProps) {
  const {
    sessionId,
    loading,
    error,
    rows,
    hasStreamTrace,
    onClearStreamTrace,
    onRewindSuccess,
  } = props;

  const [viewMode, setViewMode] = useState<TraceViewMode>("spans");
  const { t } = useI18n();

  return (
    <div className="session-trace-view">
      <CheckpointPanel sessionId={sessionId} onRewindSuccess={onRewindSuccess} />

      <div className="trace-view-toggle" role="tablist" aria-label={t("trace.viewMode")}>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === "spans"}
          className={viewMode === "spans" ? "active" : undefined}
          onClick={() => setViewMode("spans")}
        >
          {t("trace.tabSpans")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === "events"}
          className={viewMode === "events" ? "active" : undefined}
          onClick={() => setViewMode("events")}
        >
          {t("trace.tabEvents")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === "jsonl"}
          className={viewMode === "jsonl" ? "active" : undefined}
          onClick={() => setViewMode("jsonl")}
        >
          {t("trace.tabJsonl")}
        </button>
      </div>

      {viewMode === "spans" ? (
        <TraceSpanPanel
          selectedSessionId={sessionId}
          loading={loading}
          error={error}
          rows={rows}
        />
      ) : viewMode === "events" ? (
        <TracePanel
          selectedSessionId={sessionId}
          loading={loading}
          error={error}
          rows={rows}
          hasStreamTrace={hasStreamTrace}
          onClearStreamTrace={onClearStreamTrace}
        />
      ) : (
        <TraceRawJsonlPanel
          sessionId={sessionId}
          liveRows={rows}
          loading={loading}
          error={error}
          hasStreamTrace={hasStreamTrace}
        />
      )}
    </div>
  );
}
