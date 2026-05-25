import { useRef, useState } from "react";
import type { ContextSnapshot } from "../../lib/schemas";

type ContextRingProps = {
  snapshot: ContextSnapshot | null | undefined;
};

const SEGMENT_COLORS = [
  "#7c3aed", // purple  – system/static
  "#16a34a", // green   – dynamic blocks
  "#0284c7", // blue    – conversation
  "#d97706", // amber   – overflow / misc
  "#db2777", // pink    – compaction
  "#059669", // emerald
  "#9333ea", // violet
  "#ea580c", // orange
];

type Segment = { label: string; tokens: number; color: string };

function buildSegments(snapshot: ContextSnapshot): Segment[] {
  const breakdown = snapshot.context_breakdown_tokens ?? {};
  const names = snapshot.prompt_block_names ?? [];
  const segments: Segment[] = [];

  // Static prompt blocks listed in prompt_block_names
  names.forEach((name, i) => {
    const tokens = breakdown[name] ?? 0;
    if (tokens > 0) {
      segments.push({
        label: name.replace(/^\d+_/, "").replace(/\.(md|txt)$/, ""),
        tokens,
        color: SEGMENT_COLORS[i % SEGMENT_COLORS.length],
      });
    }
  });

  // Conversation: prefer breakdown entry, fall back to conversation_tokens
  const convTokens =
    breakdown["conversation"] ??
    breakdown["messages"] ??
    snapshot.conversation_tokens ??
    0;
  if (convTokens > 0) {
    segments.push({ label: "Conversation", tokens: convTokens, color: "#0284c7" });
  }

  // If breakdown is empty, fall back to coarse buckets
  if (segments.length === 0) {
    const staticTok = snapshot.static_block_tokens ?? 0;
    const dynTok = snapshot.dynamic_block_tokens ?? 0;
    const convFallback = snapshot.conversation_tokens ?? 0;
    if (staticTok > 0)
      segments.push({ label: "Static prompts", tokens: staticTok, color: "#7c3aed" });
    if (dynTok > 0)
      segments.push({ label: "Dynamic blocks", tokens: dynTok, color: "#16a34a" });
    if (convFallback > 0)
      segments.push({ label: "Conversation", tokens: convFallback, color: "#0284c7" });
  }

  return segments;
}

function formatTokens(n: number): string {
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
    // Plain ring
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

  // Multi-color arc
  const paths: React.ReactNode[] = [];
  let offset = circumference / 4; // start at top
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
  const btnRef = useRef<HTMLButtonElement>(null);

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

  const ratio = snapshot.usage_ratio ?? 0;
  const pct = Math.round(ratio * 100);
  const limit = snapshot.limit_tokens ?? 0;
  const segments = buildSegments(snapshot);

  return (
    <div className="ctx-ring-wrap">
      <button
        ref={btnRef}
        type="button"
        className="ctx-ring-btn"
        title={`Context: ${pct}% full — click for details`}
        onClick={() => setOpen((v) => !v)}
      >
        <DonutRing ratio={ratio} segments={segments} limit={limit} />
        <span className="ctx-ring-pct" style={{ color: ratio > 0.9 ? "#f85149" : ratio > 0.7 ? "#d97706" : "#8b949e" }}>
          {pct}%
        </span>
      </button>

      {open && (
        <div className="ctx-modal" role="dialog" aria-modal="true">
          <div className="ctx-modal-header">
            <span className="ctx-modal-title">Context window</span>
            <button type="button" className="ctx-modal-close" onClick={() => setOpen(false)}>
              ×
            </button>
          </div>
          <div className="ctx-modal-usage">
            <span className="ctx-modal-pct">{pct}% Full</span>
            <span className="ctx-modal-counts">
              {formatTokens(segments.reduce((a, b) => a + b.tokens, 0))} / {formatTokens(limit)} Tokens
            </span>
          </div>

          {/* Segmented bar */}
          <div className="ctx-bar">
            {segments.map((seg, i) => {
              const frac = limit > 0 ? Math.min(seg.tokens / limit, 1) : 0;
              return (
                <div
                  key={i}
                  className="ctx-bar-seg"
                  style={{ width: `${(frac * 100).toFixed(2)}%`, background: seg.color }}
                  title={`${seg.label}: ${formatTokens(seg.tokens)}`}
                />
              );
            })}
          </div>

          {/* Category list */}
          <ul className="ctx-breakdown">
            {segments.map((seg, i) => (
              <li key={i} className="ctx-breakdown-item">
                <span className="ctx-breakdown-swatch" style={{ background: seg.color }} />
                <span className="ctx-breakdown-label">{seg.label}</span>
                <span className="ctx-breakdown-count">{formatTokens(seg.tokens)}</span>
              </li>
            ))}
          </ul>

          {snapshot.compaction_threshold_tokens && (
            <div className="ctx-modal-footer">
              Compaction threshold: {formatTokens(snapshot.compaction_threshold_tokens)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
