import { useMemo, useState } from "react";
import type { TraceEventItem } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import {
  buildTraceSpanTree,
  flattenTraceSpanTree,
  formatSpanDuration,
  type TraceSpanNode,
} from "./buildTraceSpanTree";
import { TraceSpanDetail } from "./TraceSpanDetail";

type TraceSpanPanelProps = {
  selectedSessionId: string | null;
  loading: boolean;
  error: string | null;
  rows: TraceEventItem[];
};

export function TraceSpanPanel(props: TraceSpanPanelProps) {
  const { selectedSessionId, loading, error, rows } = props;
  const { t } = useI18n();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const root = useMemo(() => buildTraceSpanTree(rows), [rows]);
  const flat = useMemo(() => (root ? flattenTraceSpanTree(root) : []), [root]);
  const selectable = useMemo(() => flat.filter((n) => n.kind !== "session"), [flat]);

  const selected =
    selectable.find((n) => n.id === selectedId) ??
    selectable[selectable.length - 1] ??
    null;

  const maxDuration = root?.durationMs ?? null;

  return (
    <section className="panel trace-span-panel">
      <div className="panel-title-row">
        <div>
          <h2>{t("trace.spansTitle")}</h2>
          <p className="trace-span-subtitle">{t("trace.spansSubtitle")}</p>
        </div>
      </div>

      {!selectedSessionId ? <p>{t("trace.selectSession")}</p> : null}
      {loading ? <p>{t("trace.loading")}</p> : null}
      {error ? <p>{t("common.loadFailed", { error })}</p> : null}

      {!loading && !error && selectedSessionId && !root ? <p>{t("trace.noSpanEvents")}</p> : null}

      {root ? (
        <div className="trace-span-layout">
          <div className="trace-span-tree" role="tree" aria-label={t("trace.spanTreeLabel")}>
            {selectable.map((node) => (
              <TraceSpanRow
                key={node.id}
                node={node}
                selected={selected?.id === node.id}
                maxDuration={maxDuration}
                onSelect={() => setSelectedId(node.id)}
              />
            ))}
          </div>
          <TraceSpanDetail span={selected} sessionDurationMs={maxDuration} />
        </div>
      ) : null}
    </section>
  );
}

type TraceSpanRowProps = {
  node: TraceSpanNode;
  selected: boolean;
  maxDuration: number | null;
  onSelect: () => void;
};

function TraceSpanRow(props: TraceSpanRowProps) {
  const { node, selected, maxDuration, onSelect } = props;
  const barWidth =
    maxDuration && node.durationMs != null
      ? Math.max(0.5, (node.durationMs / maxDuration) * 100)
      : 0;
  const barOffset =
    maxDuration && maxDuration > 0 ? Math.min(100, (node.startMs / maxDuration) * 100) : 0;

  return (
    <button
      type="button"
      role="treeitem"
      aria-selected={selected}
      className={`trace-span-row trace-span-row-${node.kind}${selected ? " trace-span-row-selected" : ""}`}
      style={{ paddingLeft: `${8 + node.depth * 14}px` }}
      onClick={onSelect}
    >
      <span className={`trace-span-dot trace-span-status-${node.status}`} aria-hidden />
      <span className="trace-span-name">{node.name}</span>
      <span className="trace-span-duration">{formatSpanDuration(node.durationMs)}</span>
      <span className="trace-span-bar-track" aria-hidden>
        <span
          className="trace-span-bar-fill"
          style={{ marginLeft: `${barOffset}%`, width: `${barWidth}%` }}
        />
      </span>
    </button>
  );
}
