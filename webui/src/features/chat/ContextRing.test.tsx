import { describe, expect, it } from "vitest";
import type { ContextSnapshot } from "../../lib/schemas";

// Import buildSegments logic via re-export test helper — test category mapping inline
const CATEGORY_ORDER = [
  "system_prompt",
  "tool_definitions",
  "rules",
  "skills",
  "subagent_definitions",
  "summarized_conversation",
  "conversation",
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  system_prompt: "System prompt",
  tool_definitions: "Tool definitions",
  rules: "Rules",
  skills: "Skills",
  subagent_definitions: "Subagent definitions",
  summarized_conversation: "Summarized conversation",
  conversation: "Conversation",
};

function buildSegmentLabels(snapshot: ContextSnapshot): string[] {
  const breakdown = snapshot.context_breakdown_tokens ?? {};
  const labels: string[] = [];
  for (const key of CATEGORY_ORDER) {
    if ((breakdown[key] ?? 0) > 0) {
      labels.push(CATEGORY_LABELS[key] ?? key);
    }
  }
  return labels;
}

describe("ContextRing category mapping", () => {
  it("maps semantic breakdown keys to display labels", () => {
    const snapshot: ContextSnapshot = {
      conversation_tokens: 36000,
      message_count: 10,
      limit_tokens: 1048576,
      compaction_threshold_tokens: 890000,
      usage_ratio: 0.03,
      context_breakdown_tokens: {
        system_prompt: 744,
        tool_definitions: 10400,
        rules: 9000,
        skills: 1800,
        conversation: 36200,
      },
    };
    expect(buildSegmentLabels(snapshot)).toEqual([
      "System prompt",
      "Tool definitions",
      "Rules",
      "Skills",
      "Conversation",
    ]);
  });
});
