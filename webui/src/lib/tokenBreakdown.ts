/** Render canonical token usage_breakdown rows for Trace inspectors. */

const BREAKDOWN_ORDER = [
  "input",
  "output",
  "cache_read",
  "cache_write",
  "cache_write_5m",
  "cache_write_1h",
  "reasoning",
] as const;

export type TokenBreakdownKey = (typeof BREAKDOWN_ORDER)[number];

export function tokenBreakdownRows(
  breakdown: Record<string, unknown> | null | undefined
): Array<{ key: TokenBreakdownKey; tokens: number }> {
  if (!breakdown || typeof breakdown !== "object") return [];
  const rows: Array<{ key: TokenBreakdownKey; tokens: number }> = [];
  for (const key of BREAKDOWN_ORDER) {
    const value = breakdown[key];
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      rows.push({ key, tokens: value });
    }
  }
  return rows;
}

export function hasTokenBreakdown(breakdown: Record<string, unknown> | null | undefined): boolean {
  return tokenBreakdownRows(breakdown).length > 0;
}
