import { tokenBreakdownRows, type TokenBreakdownKey } from "../../lib/tokenBreakdown";
import { useI18n } from "../../lib/i18n";

type TokenBreakdownInspectorProps = {
  breakdown: Record<string, unknown> | null | undefined;
};

const LABEL_KEYS: Record<TokenBreakdownKey, string> = {
  input: "trace.tokenInput",
  output: "trace.tokenOutput",
  cache_read: "trace.tokenCacheRead",
  cache_write: "trace.tokenCacheWrite",
  cache_write_5m: "trace.tokenCacheWrite5m",
  cache_write_1h: "trace.tokenCacheWrite1h",
  reasoning: "trace.tokenReasoning",
};

export function TokenBreakdownInspector({ breakdown }: TokenBreakdownInspectorProps) {
  const { t } = useI18n();
  const rows = tokenBreakdownRows(breakdown);
  if (!rows.length) return null;

  return (
    <details className="trace-inspector-section" open>
      <summary>{t("trace.tokenBreakdownTitle")}</summary>
      <div className="trace-context-breakdown">
        {rows.map((row) => (
          <div key={row.key} className="trace-context-row">
            <span className="trace-context-label">{t(LABEL_KEYS[row.key])}</span>
            <span className="trace-context-tokens">{row.tokens.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </details>
  );
}
