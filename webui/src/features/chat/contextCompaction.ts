import type { ContextSnapshot } from "../../lib/schemas";

/** Best-effort total tokens used for compaction suggestion. */
export function estimateContextUsed(snapshot: ContextSnapshot): number {
  const breakdown = snapshot.context_breakdown_tokens ?? {};
  const fromBreakdown = Object.values(breakdown).reduce((sum, value) => sum + value, 0);
  if (fromBreakdown > 0) {
    return fromBreakdown;
  }
  return snapshot.conversation_tokens ?? 0;
}

export function contextUsageRatio(snapshot: ContextSnapshot): number {
  if (snapshot.usage_ratio != null) {
    return snapshot.usage_ratio;
  }
  const limit = snapshot.limit_tokens ?? 0;
  if (limit <= 0) {
    return 0;
  }
  return estimateContextUsed(snapshot) / limit;
}

/** True when manual compaction is worth surfacing in the composer. */
export function shouldSuggestCompaction(snapshot: ContextSnapshot | null | undefined): boolean {
  if (!snapshot) {
    return false;
  }
  const used = estimateContextUsed(snapshot);
  const threshold = snapshot.compaction_threshold_tokens;
  if (threshold != null && threshold > 0 && used >= threshold) {
    return true;
  }
  return contextUsageRatio(snapshot) >= 0.7;
}
