import { describe, expect, it } from "vitest";
import type { ContextSnapshot } from "../../lib/schemas";
import {
  buildContextModalModel,
  contextBarSegmentWidth,
} from "./contextModalShared";

describe("contextBarSegmentWidth", () => {
  it("uses full limit as bar denominator", () => {
    expect(contextBarSegmentWidth(381, 16000)).toBe("2.3813%");
    expect(contextBarSegmentWidth(120100, 200000)).toBe("60.05%");
  });

  it("model ratio reflects limit not just used breakdown", () => {
    const snapshot: ContextSnapshot = {
      limit_tokens: 16000,
      usage_ratio: 0.24,
      context_breakdown_tokens: {
        system_prompt: 381,
        tool_definitions: 428,
        rules: 2900,
        conversation: 112,
      },
    };
    const model = buildContextModalModel(snapshot);
    expect(model?.totalUsed).toBe(381 + 428 + 2900 + 112);
    expect(model?.pct).toBe(Math.round((model!.totalUsed / 16000) * 100));
    expect(model).not.toHaveProperty("barDenominator");
  });
});
