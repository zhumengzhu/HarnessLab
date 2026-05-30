export type ContextUsageLevel = "healthy" | "warn" | "danger";

/** Maps context fill ratio to semantic usage level (aligned with --hl-accent / warning / danger). */
export function getContextUsageLevel(ratio: number): ContextUsageLevel {
  if (ratio > 0.9) return "danger";
  if (ratio > 0.7) return "warn";
  return "healthy";
}

export function contextUsageClass(base: string, level: ContextUsageLevel): string {
  return `${base} ${base}--${level}`;
}
