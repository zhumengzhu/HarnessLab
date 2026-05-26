import { useEffect, useRef, useState } from "react";
import type { ContextSnapshot } from "../../lib/schemas";

type ContextRingProps = {
  snapshot: ContextSnapshot | null | undefined;
};

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
  subagent_definitions: "#0284c7",
  summarized_conversation: "#db2777",
  conversation: "#475569",
  messages: "#475569",
};

type Segment = { label: string; tokens: number; color: string; dimmed?: boolean };

function hasPromptMetadata(snapshot: ContextSnapshot): boolean {
  return (
    snapshot.prompt_tokens_estimate != null ||
    snapshot.static_block_tokens != null ||
    (snapshot.prompt_block_names?.length ?? 0) > 0
  );
}

function buildSegments(snapshot: ContextSnapshot): Segment[] {
  const breakdown = snapshot.context_breakdown_tokens ?? {};
  const segments: Segment[] = [];
  const seen = new Set<string>();
  const showPromptRows = hasPromptMetadata(snapshot);

  for (const key of CATEGORY_ORDER) {
    const tokens = breakdown[key] ?? 0;
    const isPromptCategory = PROMPT_CATEGORIES.has(key);
    if (tokens > 0 || (showPromptRows && isPromptCategory)) {
      segments.push({
        label: CATEGORY_LABELS[key] ?? key,
        tokens,
        color: CATEGORY_COLORS[key] ?? "#8b949e",
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
      color: "#8b949e",
    });
  }

  if (segments.length === 0) {
    const staticTok = snapshot.static_block_tokens ?? 0;
    const dynTok = snapshot.dynamic_block_tokens ?? 0;
    const convFallback = snapshot.conversation_tokens ?? 0;
    if (staticTok > 0)
      segments.push({ label: "System prompt", tokens: staticTok, color: "#6b7280" });
    if (dynTok > 0)
      segments.push({ label: "Dynamic blocks", tokens: dynTok, color: "#16a34a" });
    if (convFallback > 0)
      segments.push({ label: "Conversation", tokens: convFallback, color: "#475569" });
  }

  return segments;
}

function formatTokens(n: number): string {
  if (n <= 0) return "–";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

function DonutRing({
  ratio,
  segments,
  limit,
}: {
  ratio: number;
  segments: Segment[];
  limit: number;
}) {
  const r = 17;
  const cx = 22;
  const cy = 22;
  const circumference = 2 * Math.PI * r;
  const totalUsed = segments.reduce((a, b) => a + b.tokens, 0);

  if (segments.length === 0 || totalUsed === 0) {
    const used = circumference * Math.min(ratio, 1);
    const color = ratio > 0.9 ? "#f85149" : ratio > 0.7 ? "#d97706" : "#58a6ff";
    return (
      <svg width={44} height={44} viewBox="0 0 44 44">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#30363d" strokeWidth={5} />
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={color}
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
    <svg width={44} height={44} viewBox="0 0 44 44">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#30363d" strokeWidth={5} />
      {paths}
    </svg>
  );
}

export function ContextRing({ snapshot }: ContextRingProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      const root = wrapRef.current;
      if (root && !root.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!snapshot) {
    return (
      <button type="button" className="ctx-ring-btn ctx-ring-empty" disabled title="No context data">
        <svg width={44} height={44} viewBox="0 0 44 44">
          <circle cx={22} cy={22} r={17} fill="none" stroke="#30363d" strokeWidth={5} />
        </svg>
        <span className="ctx-ring-pct">–</span>
      </button>
    );
  }

  const limit = snapshot.limit_tokens ?? 0;
  const segments = buildSegments(snapshot);
  const totalUsed = segments.reduce((a, b) => a + b.tokens, 0);
  const barDenominator = totalUsed > 0 ? totalUsed : limit;
  const ratio = limit > 0 ? totalUsed / limit : snapshot.usage_ratio ?? 0;
  const pct = Math.round(ratio * 100);

  return (
    <div className="ctx-ring-wrap" ref={wrapRef}>
      <button
        type="button"
        className="ctx-ring-btn"
        title={`Context: ${pct}% full — click for details`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <DonutRing ratio={ratio} segments={segments} limit={limit} />
        <span
          className="ctx-ring-pct"
          style={{ color: ratio > 0.9 ? "#f85149" : ratio > 0.7 ? "#d97706" : "#8b949e" }}
        >
          {pct}%
        </span>
      </button>

      {open && (
        <div className="ctx-modal" role="dialog" aria-modal="true">
          <div className="ctx-modal-header">
            <span className="ctx-modal-title">Context</span>
            <button type="button" className="ctx-modal-close" onClick={() => setOpen(false)}>
              ×
            </button>
          </div>
          <div className="ctx-modal-usage">
            <span className="ctx-modal-pct">{pct}% Full</span>
            <span className="ctx-modal-counts">
              ~{formatTokens(totalUsed)} / {formatTokens(limit)} Tokens
            </span>
          </div>

          <div className="ctx-bar" aria-hidden={segments.length === 0}>
            {segments
              .filter((seg) => seg.tokens > 0)
              .map((seg, i, visible) => {
                const frac = barDenominator > 0 ? seg.tokens / barDenominator : 0;
                return (
                  <div
                    key={seg.label}
                    className={`ctx-bar-seg${i === 0 ? " ctx-bar-seg-first" : ""}${
                      i === visible.length - 1 ? " ctx-bar-seg-last" : ""
                    }`}
                    style={{
                      flexGrow: frac,
                      flexBasis: 0,
                      minWidth: frac > 0 ? "3px" : 0,
                      background: seg.color,
                    }}
                    title={`${seg.label}: ${formatTokens(seg.tokens)}`}
                  />
                );
              })}
          </div>

          <ul className="ctx-breakdown">
            {segments.map((seg) => (
              <li
                key={seg.label}
                className={`ctx-breakdown-item${seg.dimmed ? " ctx-breakdown-dimmed" : ""}`}
              >
                <span className="ctx-breakdown-swatch" style={{ background: seg.color }} />
                <span className="ctx-breakdown-label">{seg.label}</span>
                <span className="ctx-breakdown-count">{formatTokens(seg.tokens)}</span>
              </li>
            ))}
          </ul>

          {snapshot.compaction_threshold_tokens ? (
            <div className="ctx-modal-footer">
              Compaction threshold: {formatTokens(snapshot.compaction_threshold_tokens)}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
