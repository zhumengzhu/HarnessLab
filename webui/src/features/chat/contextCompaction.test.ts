import { describe, expect, it } from "vitest";
import {
  contextUsageRatio,
  estimateContextUsed,
  shouldSuggestCompaction,
} from "./contextCompaction";
import type { ContextSnapshot } from "../../lib/schemas";

describe("contextCompaction", () => {
  it("sums breakdown tokens when present", () => {
    const snapshot: ContextSnapshot = {
      context_breakdown_tokens: { conversation: 100, system_prompt: 50 },
      conversation_tokens: 10,
    };
    expect(estimateContextUsed(snapshot)).toBe(150);
  });

  it("suggests compaction at threshold", () => {
    expect(
      shouldSuggestCompaction({
        compaction_threshold_tokens: 800,
        context_breakdown_tokens: { conversation: 820 },
        limit_tokens: 1000,
      })
    ).toBe(true);
  });

  it("suggests compaction at 70% usage fallback", () => {
    expect(
      shouldSuggestCompaction({
        limit_tokens: 1000,
        conversation_tokens: 750,
      })
    ).toBe(true);
    expect(contextUsageRatio({ limit_tokens: 1000, conversation_tokens: 500 })).toBe(0.5);
    expect(shouldSuggestCompaction({ limit_tokens: 1000, conversation_tokens: 500 })).toBe(false);
  });
});
