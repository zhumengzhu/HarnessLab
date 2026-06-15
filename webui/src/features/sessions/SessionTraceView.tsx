import { useState } from "react";
import { useI18n } from "../../lib/i18n";
import type { ReplaySpanFocus } from "../../lib/replayFocus";
import { CheckpointPanel } from "./CheckpointPanel";
import { TraceReplayPanel } from "../trace/TraceReplayPanel";
import { TracePanel } from "../trace/TracePanel";
import { TraceSpanPanel } from "../trace/TraceSpanPanel";
import { TraceRawJsonlPanel } from "../trace/TraceRawJsonlPanel";
import type { SpanRecordItem } from "../../lib/schemas";

export type TraceViewMode = "spans" | "events" | "jsonl";

type SessionTraceViewProps = {
  sessionId: string | null;
  loading: boolean;
  error: string | null;
  spans: SpanRecordItem[];
  hasStreamSpans: boolean;
  isLive?: boolean;
  onClearStreamSpans: () => void;
  onRewindSuccess: () => void;
};

export function SessionTraceView(props: SessionTraceViewProps) {
  const {
    sessionId,
    loading,
    error,
    spans,
    hasStreamSpans,
    isLive = false,
    onClearStreamSpans,
    onRewindSuccess,
  } = props;

  const [viewMode, setViewMode] = useState<TraceViewMode>("spans");
  const [spanFocusRequest, setSpanFocusRequest] = useState<(ReplaySpanFocus & { seq: number }) | null>(
    null
  );
  const { t } = useI18n();

  return (
    <div className="session-trace-view session-trace-view-jaeger">
      <div className="trace-jaeger-chrome">
        <div className="trace-view-toggle trace-jaeger-mode-tabs" role="tablist" aria-label={t("trace.viewMode")}>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === "spans"}
          className={viewMode === "spans" ? "active" : undefined}
          onClick={() => setViewMode("spans")}
        >
          {t("trace.tabTimeline")}
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
        <details className="trace-checkpoint-fold trace-checkpoint-inline">
          <summary>{t("trace.checkpointsFold")}</summary>
          <CheckpointPanel sessionId={sessionId} onRewindSuccess={onRewindSuccess} />
        </details>
        <TraceReplayPanel
          sessionId={sessionId}
          onFocusSpan={(focus) => {
            setViewMode("spans");
            setSpanFocusRequest({ ...focus, seq: Date.now() });
          }}
        />
      </div>

      {viewMode === "spans" ? (
        <TraceSpanPanel
          selectedSessionId={sessionId}
          loading={loading}
          error={error}
          spans={spans}
          isLive={isLive}
          focusRequest={spanFocusRequest}
          onFocusHandled={() => setSpanFocusRequest(null)}
        />
      ) : viewMode === "events" ? (
        <TracePanel
          selectedSessionId={sessionId}
          loading={loading}
          error={error}
          spans={spans}
          hasStreamSpans={hasStreamSpans}
          onClearStreamSpans={onClearStreamSpans}
        />
      ) : (
        <TraceRawJsonlPanel
          sessionId={sessionId}
          liveSpans={spans}
          loading={loading}
          error={error}
          hasStreamSpans={hasStreamSpans}
        />
      )}
    </div>
  );
}
