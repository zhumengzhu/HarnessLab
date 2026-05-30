import type { ContextSnapshot } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { IconChevron } from "../shell/icons";
import {
  buildContextCompactStats,
  formatContextTokens,
} from "./contextModalShared";
import { contextUsageClass, getContextUsageLevel } from "./contextUsageLevel";

type MessageMetaDetailsProps = {
  snapshot: ContextSnapshot | null | undefined;
  modelLabel?: string | null;
  requestTokens?: number | null;
  responseTokens?: number | null;
};

export function MessageMetaDetails({
  snapshot,
  modelLabel,
  requestTokens,
  responseTokens,
}: MessageMetaDetailsProps) {
  const { t } = useI18n();
  const stats = buildContextCompactStats(snapshot, { requestTokens, responseTokens });
  if (!stats) return null;

  const { inputTokens, outputTokens, remainingTokens, pct } = stats;
  const usageLevel = getContextUsageLevel(pct / 100);
  const shortModel =
    modelLabel && modelLabel.includes("/") ? modelLabel.split("/").pop() : modelLabel;

  return (
    <details className="msg-meta msg-meta-context">
      <summary className="msg-meta__summary" title={t("chat.contextTitle")}>
        <span className="msg-meta__summary-icon" aria-hidden>
          <IconChevron size={12} />
        </span>
        <span>{t("chat.context")}</span>
      </summary>
      <div className="msg-meta__details">
        {inputTokens != null && inputTokens > 0 ? (
          <span className="msg-meta__tokens" title={t("chat.contextInput")}>
            ↑{formatContextTokens(inputTokens)}
          </span>
        ) : null}
        {outputTokens != null && outputTokens > 0 ? (
          <span className="msg-meta__tokens" title={t("chat.contextOutput")}>
            ↓{formatContextTokens(outputTokens)}
          </span>
        ) : null}
        <span className="msg-meta__tokens" title={t("chat.contextRemaining")}>
          R{formatContextTokens(remainingTokens)}
        </span>
        <span className={contextUsageClass("msg-meta__ctx", usageLevel)}>
          {pct}% ctx
        </span>
        {shortModel ? <span className="msg-meta__model">{shortModel}</span> : null}
      </div>
    </details>
  );
}
