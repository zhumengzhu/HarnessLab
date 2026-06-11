import type { SpanEventItem, SpanLinkItem, SpanRecordItem } from "../../lib/schemas";
import { spanDisplaySubtitle } from "../../lib/spanDisplay";
import { spanServiceColor } from "../../lib/spanColor";
import { spanResourceRows, spanServiceName } from "../../lib/spanResource";
import {
  formatRelativeStart,
  formatSpanDuration,
  spanStatus,
  spanTimeline,
} from "../../lib/spanTree";
import { useI18n } from "../../lib/i18n";
import { ModelCallInspector } from "./ModelCallInspector";
import { ToolSpanInspector } from "./ToolSpanInspector";
import { TraceAttributesTable } from "./TraceAttributesTable";
import { TraceDetailAccordion } from "./TraceDetailAccordion";

type TraceSpanDetailProps = {
  span: SpanRecordItem | null;
  traceStartMs: number;
  traceDurationMs: number;
  compact?: boolean;
  onClose?: () => void;
};

function attributeRows(record: SpanRecordItem): Array<[string, string]> {
  const rows: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(record.attributes ?? {})) {
    if (value == null || key === "harnesslab.live") continue;
    rows.push([key, typeof value === "object" ? JSON.stringify(value) : String(value)]);
  }
  rows.sort((a, b) => a[0].localeCompare(b[0]));
  return rows;
}

function metricRows(metrics: Record<string, unknown>): Array<[string, string]> {
  const rows: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(metrics)) {
    if (key === "context" || value == null) continue;
    rows.push([key, typeof value === "object" ? JSON.stringify(value) : String(value)]);
  }
  rows.sort((a, b) => a[0].localeCompare(b[0]));
  return rows;
}

function previewRows(rows: Array<[string, string]>, limit = 2): string {
  return rows
    .slice(0, limit)
    .map(([key, value]) => `${key}=${value.length > 24 ? `${value.slice(0, 24)}…` : value}`)
    .join(", ");
}

function eventAttributeRows(event: SpanEventItem): Array<[string, string]> {
  const rows: Array<[string, string]> = [
    ["event.name", event.name],
    ["event.time", event.time],
  ];
  for (const [key, value] of Object.entries(event.attributes ?? {})) {
    if (value == null) continue;
    rows.push([key, typeof value === "object" ? JSON.stringify(value) : String(value)]);
  }
  return rows;
}

function formatEventOffset(eventTime: string, traceStartMs: number): string {
  const ms = Date.parse(eventTime) - traceStartMs;
  if (!Number.isFinite(ms) || ms <= 0) return "+0ms";
  return `+${formatSpanDuration(ms)}`;
}

function linkAttributeRows(link: SpanLinkItem): Array<[string, string]> {
  const rows: Array<[string, string]> = [
    ["link.trace_id", link.linked_trace_id],
    ["link.span_id", link.linked_span_id],
  ];
  for (const [key, value] of Object.entries(link.attributes ?? {})) {
    if (value == null) continue;
    rows.push([key, typeof value === "object" ? JSON.stringify(value) : String(value)]);
  }
  return rows;
}

export function TraceSpanDetail({
  span,
  traceStartMs,
  traceDurationMs,
  compact = false,
  onClose,
}: TraceSpanDetailProps) {
  const { t } = useI18n();
  if (!span) {
    return (
      <div className="trace-span-detail trace-span-detail-empty">
        <p>{t("trace.selectSpan")}</p>
      </div>
    );
  }

  const status = spanStatus(span);
  const serviceName = spanServiceName(span);
  const serviceColor = spanServiceColor(serviceName);
  const subtitle = spanDisplaySubtitle(span);
  const timeline = spanTimeline(span, traceStartMs, traceDurationMs);
  const metrics = span.metrics ?? {};
  const tags = attributeRows(span);
  const processRows = spanResourceRows(span);
  const metricEntries = metricRows(metrics);
  const events = span.events ?? [];
  const links = span.links ?? [];

  return (
    <div
      className={`trace-span-detail trace-jaeger-span-detail${compact ? " trace-span-detail-compact" : ""}`}
      style={{ "--trace-service-color": serviceColor } as React.CSSProperties}
    >
      <header className="trace-jaeger-detail-header">
        <div className="trace-jaeger-detail-title-row">
          <h3 className="trace-jaeger-operation-name">{span.name}</h3>
          {status === "error" ? (
            <span className="trace-waterfall-error-icon trace-waterfall-error-icon-detail">!</span>
          ) : null}
          {onClose ? (
            <button
              type="button"
              className="trace-jaeger-detail-close"
              aria-label={t("trace.closeDetail")}
              onClick={onClose}
            >
              ×
            </button>
          ) : null}
        </div>
        {subtitle ? <p className="trace-span-detail-subtitle">{subtitle}</p> : null}
        <dl className="trace-jaeger-overview trace-jaeger-labeled-list">
          <div>
            <dt>{t("trace.detailService")}</dt>
            <dd>{serviceName}</dd>
          </div>
          <div>
            <dt>{t("trace.detailDuration")}</dt>
            <dd>{formatSpanDuration(span.duration_ms)}</dd>
          </div>
          <div>
            <dt>{t("trace.detailStartTime")}</dt>
            <dd>{formatRelativeStart(span, traceStartMs)}</dd>
          </div>
        </dl>
        <div className="trace-span-detail-bar trace-jaeger-detail-bar" aria-hidden>
          <div
            className="trace-span-detail-bar-fill trace-jaeger-detail-bar-fill"
            style={{
              marginLeft: `${timeline.offsetPct}%`,
              width: `${timeline.widthPct}%`,
            }}
          />
        </div>
      </header>

      <div className="trace-jaeger-detail-sections">
        <TraceDetailAccordion
          label={t("trace.detailTags")}
          defaultOpen
          summaryPreview={previewRows(tags)}
        >
          <TraceAttributesTable rows={tags} />
        </TraceDetailAccordion>

        <TraceDetailAccordion
          label={t("trace.detailProcess")}
          defaultOpen
          summaryPreview={previewRows(processRows)}
        >
          <TraceAttributesTable rows={processRows} />
        </TraceDetailAccordion>

        {events.length ? (
          <TraceDetailAccordion
            label={t("trace.detailEvents", { count: String(events.length) })}
            defaultOpen={events.length <= 3}
            summaryPreview={events
              .slice(0, 2)
              .map((evt) => evt.name)
              .join(", ")}
          >
            <div className="trace-detail-events">
              {events.map((event, index) => {
                const eventRows = eventAttributeRows(event);
                const rel = formatEventOffset(event.time, traceStartMs);
                return (
                  <TraceDetailAccordion
                    key={`${event.name}-${event.time}-${index}`}
                    label={`${event.name} (${rel})`}
                    defaultOpen={index === 0 && events.length === 1}
                    summaryPreview={previewRows(eventRows.slice(2), 1)}
                  >
                    <TraceAttributesTable rows={eventRows} />
                  </TraceDetailAccordion>
                );
              })}
            </div>
          </TraceDetailAccordion>
        ) : null}

        {metricEntries.length ? (
          <TraceDetailAccordion
            label={t("trace.detailMetrics")}
            summaryPreview={previewRows(metricEntries)}
          >
            <TraceAttributesTable rows={metricEntries} />
          </TraceDetailAccordion>
        ) : null}

        {span.name === "llm.generate" ? (
          <TraceDetailAccordion label={t("trace.detailPrompt")}>
            <ModelCallInspector
              payload={{
                ...metrics,
                decision_kind: span.attributes["harnesslab.decision.kind"],
              }}
            />
          </TraceDetailAccordion>
        ) : null}

        {span.name.startsWith("tool.") && !span.name.startsWith("tool.hooks.") ? (
          <TraceDetailAccordion label={t("trace.detailToolIo")} defaultOpen>
            <ToolSpanInspector
              metrics={metrics}
              sessionId={span.session_id}
              toolName={String(span.attributes["harnesslab.tool.name"] ?? span.name.slice(5))}
            />
          </TraceDetailAccordion>
        ) : null}

        {links.length ? (
          <TraceDetailAccordion
            label={t("trace.spanLinks", { count: String(links.length) })}
            summaryPreview={links
              .slice(0, 2)
              .map((link) => String(link.attributes?.["harnesslab.link.kind"] ?? "link"))
              .join(", ")}
          >
            <div className="trace-detail-events">
              {links.map((link, index) => (
                <TraceDetailAccordion
                  key={`${link.linked_trace_id}-${link.linked_span_id}-${index}`}
                  label={String(link.attributes?.["harnesslab.link.kind"] ?? "link")}
                  summaryPreview={`${link.linked_trace_id.slice(0, 8)}:${link.linked_span_id.slice(0, 8)}`}
                >
                  <TraceAttributesTable rows={linkAttributeRows(link)} />
                </TraceDetailAccordion>
              ))}
            </div>
          </TraceDetailAccordion>
        ) : null}

        <footer className="trace-jaeger-detail-footer">
          <code title={span.span_id}>{span.span_id}</code>
          <span className="trace-jaeger-detail-footer-meta">
            trace {span.trace_id.slice(0, 12)}… · turn {span.turn_index}
          </span>
        </footer>
      </div>
    </div>
  );
}
