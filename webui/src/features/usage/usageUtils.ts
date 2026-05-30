import type { UsageDailyBucket, UsageTotals } from "../../lib/schemas";

export const USAGE_DIMENSION_KEYS = [
  "cache_read",
  "cache_write",
  "cache_write_5m",
  "cache_write_1h",
  "reasoning",
] as const;

export type UsageDimensionKey = (typeof USAGE_DIMENSION_KEYS)[number];

export function formatCompactNumber(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  }
  return String(Math.round(value));
}

export function formatUsd(value: number): string {
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(2)}`;
  if (value > 0) return `$${value.toFixed(4)}`;
  return "$0.00";
}

export function formatCost(
  costUsd: number,
  costDisplay: number | null | undefined,
  currencySymbol: string | undefined,
  displayCurrency: string | undefined
): string {
  if (
    displayCurrency &&
    displayCurrency !== "USD" &&
    typeof costDisplay === "number" &&
    Number.isFinite(costDisplay)
  ) {
    const symbol = currencySymbol ?? displayCurrency;
    if (costDisplay >= 1) return `${symbol}${costDisplay.toFixed(2)}`;
    if (costDisplay >= 0.01) return `${symbol}${costDisplay.toFixed(2)}`;
    if (costDisplay > 0) return `${symbol}${costDisplay.toFixed(4)}`;
    return `${symbol}0.00`;
  }
  return formatUsd(costUsd);
}

export function activeUsageDimensions(
  dimensions: Record<string, number> | undefined
): { key: UsageDimensionKey; value: number }[] {
  if (!dimensions) return [];
  return USAGE_DIMENSION_KEYS.filter((key) => (dimensions[key] ?? 0) > 0).map((key) => ({
    key,
    value: dimensions[key] ?? 0,
  }));
}

export function formatShortDate(isoDate: string): string {
  const date = new Date(`${isoDate}T12:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function dailyBarValue(
  day: UsageDailyBucket,
  metric: "tokens" | "cost",
  chartView: "total" | "byType"
): number {
  if (metric === "cost") {
    return day.cost_display ?? day.cost_usd;
  }
  if (chartView === "byType") return day.input_tokens + day.output_tokens;
  return day.total_tokens;
}

export function maxDailyBarValue(
  daily: UsageDailyBucket[],
  metric: "tokens" | "cost",
  chartView: "total" | "byType"
): number {
  if (daily.length === 0) return 1;
  return Math.max(
    1,
    ...daily.map((day) => dailyBarValue(day, metric, chartView))
  );
}

export function typeShare(totals: UsageTotals, field: "input_tokens" | "output_tokens"): number {
  const sum = totals.input_tokens + totals.output_tokens;
  if (sum <= 0) return 0;
  return totals[field] / sum;
}
