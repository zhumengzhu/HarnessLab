import { useEffect, useMemo, useRef, useState } from "react";
import type { SpanRecordItem } from "../../lib/schemas";
import { isLiveSpan } from "../../lib/liveSpans";
import { spanServiceColor } from "../../lib/spanColor";
import { spanServiceName } from "../../lib/spanResource";
import { useI18n } from "../../lib/i18n";
import { spanOperationHint, spanOperationName } from "../../lib/spanDisplay";
import { spanMatchesDeepQuery } from "../../lib/spanSearch";
import { aggregateTurnLlmMetrics } from "../../lib/traceMetrics";
import { PromptDiffPanel } from "./PromptDiffPanel";
import {
  buildTimelineTicks,
  collectCollapsibleSpanIds,
  flattenSpanTree,
  formatSpanDuration,
  groupSpansByTrace,
  spanStatus,
  spanTimeline,
  type SpanTreeNode,
} from "../../lib/spanTree";
import { TraceSpanDetail } from "./TraceSpanDetail";

type TraceSpanPanelProps = {
  selectedSessionId: string | null;
  loading: boolean;
  error: string | null;
  spans: SpanRecordItem[];
  isLive?: boolean;
};

export function TraceSpanPanel(props: TraceSpanPanelProps) {
  const { selectedSessionId, loading, error, spans, isLive = false } = props;
  const { t } = useI18n();
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => new Set());
  const [nameFilter, setNameFilter] = useState("");
  const [detailOpen, setDetailOpen] = useState(true);
  const [liveTick, setLiveTick] = useState(0);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isLive) return;
    const id = window.setInterval(() => setLiveTick((n) => n + 1), 500);
    return () => window.clearInterval(id);
  }, [isLive]);

  const traceGroups = useMemo(() => groupSpansByTrace(spans), [spans, liveTick]);
  const activeTrace =
    traceGroups.find((group) => group.traceId === selectedTraceId) ??
    traceGroups[traceGroups.length - 1] ??
    null;

  const flat = useMemo(() => {
    if (!activeTrace) return [];
    return flattenSpanTree(activeTrace.root, collapsedIds);
  }, [activeTrace, collapsedIds, liveTick]);

  const filteredFlat = useMemo(() => {
    const q = nameFilter.trim();
    if (!q) return flat;
    return flat.filter(({ node }) => spanMatchesDeepQuery(node.span, q));
  }, [flat, nameFilter]);

  const turnSummary = useMemo(
    () => aggregateTurnLlmMetrics(spans, activeTrace?.traceId ?? null),
    [spans, activeTrace?.traceId]
  );

  const selectedNode: SpanTreeNode | null =
    filteredFlat.find((row) => row.node.span.span_id === selectedSpanId)?.node ??
    filteredFlat[filteredFlat.length - 1]?.node ??
    null;

  const collapsibleIds = useMemo(
    () => (activeTrace ? collectCollapsibleSpanIds(activeTrace.root) : []),
    [activeTrace]
  );

  const timelineTicks = useMemo(
    () => (activeTrace ? buildTimelineTicks(activeTrace.traceDurationMs) : []),
    [activeTrace, liveTick]
  );

  const liveSpanCount = useMemo(() => spans.filter(isLiveSpan).length, [spans]);

  const traceServiceName = useMemo(
    () => (activeTrace ? spanServiceName(activeTrace.root.span) : "harnesslab"),
    [activeTrace]
  );

  useEffect(() => {
    if (activeTrace) {
      setSelectedSpanId(activeTrace.root.span.span_id);
    }
  }, [activeTrace?.traceId]);

  useEffect(() => {
    if (!isLive || !bodyRef.current) return;
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [filteredFlat.length, isLive]);

  const toggleCollapsed = (spanId: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(spanId)) next.delete(spanId);
      else next.add(spanId);
      return next;
    });
  };

  const handleTreeKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!filteredFlat.length) return;
    const currentIndex = filteredFlat.findIndex(
      (row) => row.node.span.span_id === selectedNode?.span.span_id
    );
    if (event.key === "ArrowDown") {
      event.preventDefault();
      const next = filteredFlat[Math.min(currentIndex + 1, filteredFlat.length - 1)] ?? filteredFlat[0];
      setSelectedSpanId(next.node.span.span_id);
      setDetailOpen(true);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      const prev =
        filteredFlat[Math.max(currentIndex - 1, 0)] ?? filteredFlat[filteredFlat.length - 1];
      setSelectedSpanId(prev.node.span.span_id);
      setDetailOpen(true);
    } else if (event.key === "ArrowRight") {
      const row = filteredFlat[currentIndex];
      if (row?.hasChildren && row.collapsed) {
        event.preventDefault();
        toggleCollapsed(row.node.span.span_id);
      }
    } else if (event.key === "ArrowLeft") {
      const row = filteredFlat[currentIndex];
      if (row?.hasChildren && !row.collapsed) {
        event.preventDefault();
        toggleCollapsed(row.node.span.span_id);
      }
    }
  };

  return (
    <section className="trace-jaeger-panel">
      <header className="trace-jaeger-toolbar">
        <div className="trace-jaeger-toolbar-left">
          {isLive || liveSpanCount > 0 ? (
            <span className="trace-jaeger-live-badge">{t("trace.liveBadge")}</span>
          ) : null}
          {activeTrace ? (
            <>
              <span className="trace-jaeger-process-chip" title={traceServiceName}>
                {traceServiceName}
              </span>
              <span className="trace-jaeger-stat">
                {t("trace.traceDuration", { duration: formatSpanDuration(activeTrace.traceDurationMs) })}
              </span>
              <span className="trace-jaeger-stat">
                {t("trace.spanCount", { count: String(filteredFlat.length) })}
              </span>
              {turnSummary.llmCalls > 0 ? (
                <span className="trace-jaeger-stat trace-jaeger-token-stat">
                  {t("trace.turnTokens", {
                    input: String(turnSummary.inputTokens),
                    output: String(turnSummary.outputTokens),
                    total: String(turnSummary.totalTokens || turnSummary.inputTokens + turnSummary.outputTokens),
                  })}
                  {turnSummary.costUsd != null
                    ? ` · $${turnSummary.costUsd.toFixed(4)}`
                    : ""}
                </span>
              ) : null}
            </>
          ) : null}
        </div>
        <div className="trace-jaeger-toolbar-right">
          {traceGroups.length > 1 ? (
            <label className="trace-turn-select trace-jaeger-turn-select">
              <span>{t("trace.turnSelect")}</span>
              <select
                value={activeTrace?.traceId ?? ""}
                onChange={(event) => {
                  setSelectedTraceId(event.target.value);
                  setSelectedSpanId(null);
                }}
              >
                {traceGroups.map((group) => (
                  <option key={group.traceId} value={group.traceId}>
                    {t("trace.turnOption", {
                      index: String(group.turnIndex),
                      duration: formatSpanDuration(group.traceDurationMs),
                    })}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="trace-jaeger-filter">
            <input
              type="search"
              value={nameFilter}
              placeholder={t("trace.spanFilterPlaceholder")}
              onChange={(event) => setNameFilter(event.target.value)}
            />
          </label>
          <button type="button" disabled={!collapsibleIds.length} onClick={() => setCollapsedIds(new Set())}>
            {t("trace.expandAll")}
          </button>
          <button
            type="button"
            disabled={!collapsibleIds.length}
            onClick={() => setCollapsedIds(new Set(collapsibleIds))}
          >
            {t("trace.collapseAll")}
          </button>
          <button type="button" onClick={() => setDetailOpen((open) => !open)}>
            {detailOpen ? t("trace.hideDetail") : t("trace.showDetail")}
          </button>
        </div>
      </header>

      <PromptDiffPanel spans={spans} />

      {!selectedSessionId ? <p className="trace-span-hint">{t("trace.selectSession")}</p> : null}
      {loading ? <p className="trace-span-hint">{t("trace.loading")}</p> : null}
      {error ? <p className="trace-span-hint trace-span-hint-error">{t("common.loadFailed", { error })}</p> : null}

      {!loading && !error && selectedSessionId && !activeTrace ? (
        <p className="trace-span-hint">{t("trace.noSpanEvents")}</p>
      ) : null}

      {activeTrace ? (
        <div className="trace-jaeger-shell">
          <div className="trace-jaeger-waterfall">
            <div className="trace-waterfall-head trace-jaeger-head" aria-hidden>
              <div className="trace-waterfall-col trace-waterfall-col-op">{t("trace.colServiceOp")}</div>
              <div className="trace-waterfall-col trace-waterfall-col-time">
                <div className="trace-waterfall-ruler trace-jaeger-ruler">
                  {timelineTicks.map((tick) => (
                    <span
                      key={`${tick.pct}-${tick.label}`}
                      className="trace-waterfall-tick"
                      style={{ left: `${tick.pct}%` }}
                    >
                      {tick.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div
              ref={bodyRef}
              className="trace-waterfall-body trace-jaeger-body"
              role="tree"
              tabIndex={0}
              aria-label={t("trace.spanTreeLabel")}
              onKeyDown={handleTreeKeyDown}
            >
              {!filteredFlat.length ? (
                <p className="trace-span-tree-empty">{t("trace.spanFilterEmpty")}</p>
              ) : null}
              {filteredFlat.map(({ node, collapsed, hasChildren }) => {
                const span = node.span;
                const status = spanStatus(span);
                const serviceName = spanServiceName(span);
                const serviceColor = spanServiceColor(serviceName);
                const operation = spanOperationName(span);
                const operationHint = spanOperationHint(span);
                const showService = serviceName !== traceServiceName;
                const timeline = spanTimeline(
                  span,
                  activeTrace.traceStartMs,
                  activeTrace.traceDurationMs
                );
                const selected = selectedNode?.span.span_id === span.span_id;
                const live = isLiveSpan(span);
                const durationLabel = live
                  ? t("trace.running")
                  : formatSpanDuration(span.duration_ms);

                return (
                  <div
                    key={span.span_id}
                    className={`trace-waterfall-row trace-jaeger-span-row${
                      selected ? " trace-waterfall-row-selected" : ""
                    }${live ? " trace-waterfall-row-live" : ""}${
                      status === "error" ? " trace-waterfall-row-error" : ""
                    }`}
                    style={
                      {
                        "--trace-depth": node.depth,
                        "--trace-service-color": serviceColor,
                      } as React.CSSProperties
                    }
                  >
                    {hasChildren ? (
                      <button
                        type="button"
                        className="trace-waterfall-toggle-btn"
                        aria-label={collapsed ? t("trace.expandSpan") : t("trace.collapseSpan")}
                        onClick={() => toggleCollapsed(span.span_id)}
                      >
                        {collapsed ? "▸" : "▾"}
                      </button>
                    ) : (
                      <span className="trace-waterfall-toggle-btn trace-waterfall-toggle-empty" aria-hidden />
                    )}
                    <button
                      type="button"
                      role="treeitem"
                      aria-selected={selected}
                      className="trace-waterfall-row-btn trace-jaeger-row-btn"
                      onClick={() => {
                        setSelectedSpanId(span.span_id);
                        setDetailOpen(true);
                      }}
                    >
                      <div className="trace-waterfall-col trace-waterfall-col-op trace-jaeger-name-col">
                        {status === "error" ? (
                          <span className="trace-waterfall-error-icon" aria-hidden>
                            !
                          </span>
                        ) : null}
                        <span
                          className="trace-waterfall-span-name"
                          style={{ borderLeftColor: serviceColor }}
                        >
                          {showService ? (
                            <span className="trace-waterfall-svc-name">{serviceName}</span>
                          ) : null}
                          <small className="trace-waterfall-endpoint-name">{operation}</small>
                          {operationHint ? (
                            <span className="trace-waterfall-op-hint">{operationHint}</span>
                          ) : null}
                        </span>
                      </div>
                      <div className="trace-waterfall-col trace-waterfall-col-time trace-jaeger-span-view">
                        <div className="trace-waterfall-bar-track trace-jaeger-bar-track">
                          <div
                            className={`trace-waterfall-bar trace-jaeger-bar${
                              live ? " trace-waterfall-bar-live" : ""
                            }${status === "error" ? " trace-jaeger-bar-error" : ""}`}
                            style={{
                              marginLeft: `${timeline.offsetPct}%`,
                              width: `${timeline.widthPct}%`,
                              background: serviceColor,
                            }}
                          />
                          <span
                            className="trace-waterfall-bar-label"
                            style={{ left: `calc(${timeline.offsetPct}% + ${timeline.widthPct}% + 4px)` }}
                          >
                            {durationLabel}
                          </span>
                        </div>
                      </div>
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          <aside
            className={`trace-jaeger-detail-pane${detailOpen ? "" : " trace-jaeger-detail-collapsed"}`}
            aria-label={t("trace.spanDetailTitle")}
            aria-hidden={!detailOpen}
          >
            {detailOpen ? (
              <TraceSpanDetail
                span={selectedNode?.span ?? null}
                traceStartMs={activeTrace.traceStartMs}
                traceDurationMs={activeTrace.traceDurationMs}
                compact
                onClose={() => setDetailOpen(false)}
              />
            ) : null}
          </aside>
        </div>
      ) : null}
    </section>
  );
}
