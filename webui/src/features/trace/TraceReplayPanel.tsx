import { useState } from "react";
import { apiPost } from "../../lib/api-client";
import { replayFocusFromDivergence } from "../../lib/replayFocus";
import type { ReplayResponse } from "../../lib/schemas";
import type { ReplaySpanFocus } from "../../lib/replayFocus";
import { useI18n } from "../../lib/i18n";

type TraceReplayPanelProps = {
  sessionId: string | null;
  onFocusSpan?: (focus: ReplaySpanFocus) => void;
};

export function TraceReplayPanel({ sessionId, onFocusSpan }: TraceReplayPanelProps) {
  const { t } = useI18n();
  const [strict, setStrict] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReplayResponse | null>(null);

  async function runReplay() {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await apiPost<ReplayResponse>(
        `/api/sessions/${encodeURIComponent(sessionId)}/replay`,
        { strict }
      );
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  function focusDivergence(row: ReplayResponse["divergences"][number]) {
    const focus = replayFocusFromDivergence(row);
    if (focus && onFocusSpan) {
      onFocusSpan(focus);
    }
  }

  return (
    <details className="trace-replay-fold">
      <summary>{t("trace.replayFold")}</summary>
      <div className="trace-replay-body">
        {!sessionId ? <p>{t("trace.selectSession")}</p> : null}
        {sessionId ? (
          <>
            <label className="trace-replay-strict">
              <input
                type="checkbox"
                checked={strict}
                onChange={(event) => setStrict(event.target.checked)}
              />
              {t("trace.replayStrict")}
            </label>
            <button type="button" disabled={loading} onClick={() => void runReplay()}>
              {loading ? t("trace.replayRunning") : t("trace.replayRun")}
            </button>
          </>
        ) : null}
        {error ? <p className="error-text">{error}</p> : null}
        {result ? (
          <div className={`trace-replay-result${result.matched ? " trace-replay-ok" : " trace-replay-fail"}`}>
            {result.unreplayable ? (
              <p className="error-text">{t("trace.replayUnreplayable", { reason: result.unreplayable })}</p>
            ) : (
              <p>
                {result.matched
                  ? t("trace.replayMatched", {
                      count: String(result.original_len),
                    })
                  : t("trace.replayDiverged", {
                      count: String(result.divergences.length),
                      original: String(result.original_len),
                      replayed: String(result.replayed_len),
                    })}
              </p>
            )}
            {result.divergences.length ? (
              <ul className="trace-replay-divergences">
                {result.divergences.map((row) => (
                  <li key={`${row.index}-${row.kind}-${row.detail.slice(0, 24)}`}>
                    {onFocusSpan ? (
                      <button
                        type="button"
                        className="trace-replay-jump"
                        title={t("trace.replayJumpToSpan")}
                        onClick={() => focusDivergence(row)}
                      >
                        <code>[{row.index}] {row.kind}</code> {row.detail}
                      </button>
                    ) : (
                      <>
                        <code>[{row.index}] {row.kind}</code> {row.detail}
                      </>
                    )}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </details>
  );
}
