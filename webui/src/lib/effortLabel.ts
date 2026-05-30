import type { ModelInfo } from "./schemas";

export function formatEffortLabel(
  effort: string | null | undefined,
  model?: ModelInfo
): string | null {
  if (!effort) return null;
  if (model?.backend === "deepseek") {
    if (effort === "disabled") return "Off";
    if (effort === "high") return "High";
    if (effort === "max") return "Max";
    if (effort === "enabled") return "High";
  }
  if (model?.thinking_schema === "toggle") {
    if (effort === "disabled") return "Off";
    if (effort === "enabled") return "Thinking";
  }
  if (effort === "minimal") return "Minimal";
  return effort.charAt(0).toUpperCase() + effort.slice(1);
}
