/** Map replay divergence rows to Trace span focus hints. */

import type { ReplayDivergenceItem } from "./schemas";

export type ReplaySpanFocus = {
  turnIndex: number;
  spanNameHint?: string;
};

const TURN_PATH = /turn\[(\d+)\]/;
const SPAN_NAME = /\/([a-zA-Z0-9_.-]+)(?:\[\d+\])?(?:[:/]|$)/;

export function replayFocusFromDivergence(row: ReplayDivergenceItem): ReplaySpanFocus | null {
  const turnMatch = row.detail.match(TURN_PATH);
  const turnIndex = turnMatch ? Number.parseInt(turnMatch[1] ?? "", 10) : row.index;
  if (!Number.isFinite(turnIndex) || turnIndex < 0) {
    return null;
  }

  const nameMatch = row.detail.match(SPAN_NAME);
  const spanNameHint = nameMatch?.[1];
  return { turnIndex, spanNameHint };
}
