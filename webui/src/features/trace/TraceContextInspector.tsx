import type { ContextSnapshot } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { buildSegments, contextSegmentLabel } from "../chat/contextModalShared";

type TraceContextInspectorProps = {
  context: Record<string, unknown> | ContextSnapshot | null;
};

export function TraceContextInspector({ context }: TraceContextInspectorProps) {
  const { t } = useI18n();
  if (!context || typeof context !== "object") return null;

  const snapshot = context as ContextSnapshot;
  const limit = snapshot.limit_tokens ?? 0;
  const segments = buildSegments(snapshot);
  const used =
    snapshot.conversation_tokens ??
    segments.reduce((sum, seg) => sum + seg.tokens, 0);
  const ratio = limit > 0 ? used / limit : snapshot.usage_ratio ?? 0;
  const pct = Math.min(100, Math.round(ratio * 100));

  if (!segments.length && !limit) return null;

  return (
    <details className="trace-inspector-section" open>
      <summary>
        {t("trace.contextTitle")} · {used.toLocaleString()}
        {limit ? ` / ${limit.toLocaleString()} (${pct}%)` : ""}
      </summary>
      <div className="trace-context-breakdown">
        {segments.map((segment) => (
          <div key={`${segment.categoryId ?? segment.label}-${segment.tokens}`} className="trace-context-row">
            <span className="trace-context-label">{contextSegmentLabel(segment, t)}</span>
            <span className="trace-context-tokens">{segment.tokens.toLocaleString()}</span>
          </div>
        ))}
        {snapshot.prompt_block_names?.length ? (
          <p className="trace-context-blocks">
            {t("trace.contextBlocks")}: {snapshot.prompt_block_names.join(", ")}
          </p>
        ) : null}
      </div>
    </details>
  );
}
