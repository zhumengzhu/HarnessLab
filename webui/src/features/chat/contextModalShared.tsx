import type { ContextSnapshot } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import {
  contextUsageClass,
  getContextUsageLevel,
} from "./contextUsageLevel";

const CATEGORY_ORDER = [
  "system_prompt",
  "tool_definitions",
  "rules",
  "skills",
  "subagent_definitions",
  "summarized_conversation",
  "conversation",
] as const;

const PROMPT_CATEGORIES = new Set([
  "system_prompt",
  "tool_definitions",
  "rules",
  "skills",
  "subagent_definitions",
]);

const CATEGORY_LABELS: Record<string, string> = {
  system_prompt: "System prompt",
  tool_definitions: "Tool definitions",
  rules: "Rules",
  skills: "Skills",
  subagent_definitions: "Subagent definitions",
  summarized_conversation: "Summarized conversation",
  conversation: "Conversation",
  messages: "Conversation",
};

const CATEGORY_COLORS: Record<string, string> = {
  system_prompt: "#6b7280",
  tool_definitions: "#7c3aed",
  rules: "#16a34a",
  skills: "#d97706",
  subagent_definitions: "#be123c",
  summarized_conversation: "#db2777",
  conversation: "#475569",
  messages: "#475569",
};

export type ContextSegment = { categoryId?: string; label: string; tokens: number; color: string; dimmed?: boolean };

const CONTEXT_CATEGORY_I18N: Record<string, string> = {
  system_prompt: "context.systemPrompt",
  tool_definitions: "context.toolDefinitions",
  rules: "context.rules",
  skills: "context.skills",
  subagent_definitions: "context.subagentDefinitions",
  summarized_conversation: "context.summarizedConversation",
  conversation: "context.conversation",
  messages: "context.conversation",
  dynamic_blocks: "context.dynamicBlocks",
};

export function contextSegmentLabel(
  segment: ContextSegment,
  t: (key: string) => string
): string {
  if (segment.categoryId && CONTEXT_CATEGORY_I18N[segment.categoryId]) {
    return t(CONTEXT_CATEGORY_I18N[segment.categoryId]);
  }
  return segment.label;
}

export type ContextModalModel = {
  snapshot: ContextSnapshot;
  limit: number;
  segments: ContextSegment[];
  totalUsed: number;
  ratio: number;
  pct: number;
};

function hasPromptMetadata(snapshot: ContextSnapshot): boolean {
  return (
    snapshot.prompt_tokens_estimate != null ||
    snapshot.static_block_tokens != null ||
    (snapshot.prompt_block_names?.length ?? 0) > 0
  );
}

export function buildSegments(snapshot: ContextSnapshot): ContextSegment[] {
  const breakdown = snapshot.context_breakdown_tokens ?? {};
  const segments: ContextSegment[] = [];
  const seen = new Set<string>();
  const showPromptRows = hasPromptMetadata(snapshot);

  for (const key of CATEGORY_ORDER) {
    const tokens = breakdown[key] ?? 0;
    const isPromptCategory = PROMPT_CATEGORIES.has(key);
    if (tokens > 0 || (showPromptRows && isPromptCategory)) {
      segments.push({
        categoryId: key,
        label: CATEGORY_LABELS[key] ?? key,
        tokens,
        color: CATEGORY_COLORS[key] ?? "var(--hl-text-muted)",
        dimmed: tokens === 0,
      });
      seen.add(key);
    }
  }

  for (const [key, tokens] of Object.entries(breakdown)) {
    if (seen.has(key) || key === "messages" || tokens <= 0) continue;
    segments.push({
      label: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      tokens,
      color: "var(--hl-text-muted)",
    });
  }

  if (segments.length === 0) {
    const staticTok = snapshot.static_block_tokens ?? 0;
    const dynTok = snapshot.dynamic_block_tokens ?? 0;
    const convFallback = snapshot.conversation_tokens ?? 0;
    if (staticTok > 0)
      segments.push({ categoryId: "system_prompt", label: "System prompt", tokens: staticTok, color: "#6b7280" });
    if (dynTok > 0)
      segments.push({ categoryId: "dynamic_blocks", label: "Dynamic blocks", tokens: dynTok, color: "#16a34a" });
    if (convFallback > 0)
      segments.push({ categoryId: "conversation", label: "Conversation", tokens: convFallback, color: "#475569" });
  }

  return segments;
}

export function formatContextTokens(n: number): string {
  if (n <= 0) return "–";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export function buildContextModalModel(
  snapshot: ContextSnapshot | null | undefined
): ContextModalModel | null {
  if (!snapshot) return null;
  const limit = snapshot.limit_tokens ?? 0;
  const segments = buildSegments(snapshot);
  const totalUsed = segments.reduce((a, b) => a + b.tokens, 0);
  const ratio = limit > 0 ? totalUsed / limit : snapshot.usage_ratio ?? 0;
  const pct = Math.round(ratio * 100);
  return { snapshot, limit, segments, totalUsed, ratio, pct };
}

export type ContextCompactStats = {
  inputTokens: number | null;
  outputTokens: number | null;
  remainingTokens: number;
  pct: number;
};

/** OpenClaw-style one-line context stats for message footers. */
export function buildContextCompactStats(
  snapshot: ContextSnapshot | null | undefined,
  turnTokens?: { requestTokens?: number | null; responseTokens?: number | null }
): ContextCompactStats | null {
  const model = buildContextModalModel(snapshot);
  if (!model) return null;
  const { limit, totalUsed, pct } = model;
  const inputTokens =
    turnTokens?.requestTokens ??
    snapshot?.prompt_tokens_estimate ??
    (totalUsed > 0 ? totalUsed : snapshot?.conversation_tokens ?? null);
  const outputTokens = turnTokens?.responseTokens ?? null;
  const remainingTokens = Math.max(0, limit - totalUsed);
  return { inputTokens, outputTokens, remainingTokens, pct };
}

/** Width of a bar segment as share of the full context limit (Cursor-style). */
export function contextBarSegmentWidth(tokens: number, limit: number): string {
  if (limit <= 0 || tokens <= 0) return "0%";
  const pct = Math.min((tokens / limit) * 100, 100);
  return `${+pct.toFixed(4)}%`;
}

export function DonutRing({
  ratio,
  segments,
  limit,
}: {
  ratio: number;
  segments: ContextSegment[];
  limit: number;
}) {
  const r = 17;
  const cx = 22;
  const cy = 22;
  const circumference = 2 * Math.PI * r;
  const totalUsed = segments.reduce((a, b) => a + b.tokens, 0);

  if (segments.length === 0 || totalUsed === 0) {
    const used = circumference * Math.min(ratio, 1);
    const level = getContextUsageLevel(ratio);
    return (
      <svg width={44} height={44} viewBox="0 0 44 44" className="ctx-ring-svg">
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          className="ctx-ring-track"
          strokeWidth={5}
        />
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          className={contextUsageClass("ctx-ring-fill", level)}
          strokeWidth={5}
          strokeDasharray={`${used} ${circumference - used}`}
          strokeDashoffset={circumference / 4}
          strokeLinecap="round"
        />
      </svg>
    );
  }

  const paths: React.ReactNode[] = [];
  let offset = circumference / 4;
  segments.forEach((seg, i) => {
    const frac = limit > 0 ? seg.tokens / limit : 0;
    const len = circumference * Math.min(frac, 1);
    paths.push(
      <circle
        key={i}
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke={seg.color}
        strokeWidth={5}
        strokeDasharray={`${len} ${circumference - len}`}
        strokeDashoffset={offset}
        strokeLinecap="butt"
      />
    );
    offset -= len;
  });

  return (
    <svg width={44} height={44} viewBox="0 0 44 44" className="ctx-ring-svg">
      <circle cx={cx} cy={cy} r={r} fill="none" className="ctx-ring-track" strokeWidth={5} />
      {paths}
    </svg>
  );
}

export function ContextBreakdownBody({ model }: { model: ContextModalModel }) {
  const { t } = useI18n();
  const { snapshot, limit, segments, totalUsed, pct, ratio } = model;
  const usageLevel = getContextUsageLevel(ratio);
  const filledSegments = segments.filter((seg) => seg.tokens > 0);

  return (
    <>
      <div className="ctx-modal-usage">
        <span className={contextUsageClass("ctx-modal-pct", usageLevel)}>
          {t("chat.contextFull", { pct })}
        </span>
        <span className="ctx-modal-counts">
          {t("chat.contextTokensRatio", {
            used: formatContextTokens(totalUsed),
            limit: formatContextTokens(limit),
          })}
        </span>
      </div>

      <div className="ctx-bar" aria-hidden={filledSegments.length === 0}>
        {filledSegments.map((seg, index) => (
          <div
            key={seg.label}
            className={`ctx-bar-seg${index === 0 ? " ctx-bar-seg-first" : ""}`}
            style={{
              width: contextBarSegmentWidth(seg.tokens, limit),
              flexShrink: 0,
              background: seg.color,
            }}
            title={`${contextSegmentLabel(seg, t)}: ${formatContextTokens(seg.tokens)}`}
          />
        ))}
      </div>

      <ul className="ctx-breakdown">
        {segments.map((seg) => (
          <li
            key={seg.label}
            className={`ctx-breakdown-item${seg.dimmed ? " ctx-breakdown-dimmed" : ""}`}
          >
            <span className="ctx-breakdown-swatch" style={{ background: seg.color }} />
            <span className="ctx-breakdown-label">{contextSegmentLabel(seg, t)}</span>
            <span className="ctx-breakdown-count">{formatContextTokens(seg.tokens)}</span>
          </li>
        ))}
      </ul>

      {snapshot.compaction_threshold_tokens ? (
        <div className="ctx-modal-footer">
          {t("chat.contextCompactionThreshold", {
            tokens: formatContextTokens(snapshot.compaction_threshold_tokens),
          })}
        </div>
      ) : null}
    </>
  );
}

export function ContextModalPanel({
  model,
  onClose,
  className,
}: {
  model: ContextModalModel;
  onClose: () => void;
  className?: string;
}) {
  const { t } = useI18n();
  return (
    <div className={`ctx-modal${className ? ` ${className}` : ""}`} role="dialog" aria-modal="true">
      <div className="ctx-modal-header">
        <span className="ctx-modal-title">{t("context.title")}</span>
        <button type="button" className="ctx-modal-close" onClick={onClose}>
          ×
        </button>
      </div>
      <ContextBreakdownBody model={model} />
    </div>
  );
}
