import { describe, expect, it } from "vitest";
import {
  dailyBarValue,
  formatCompactNumber,
  formatCost,
  formatShortDate,
  formatUsd,
  activeUsageDimensions,
  maxDailyBarValue,
  typeShare,
} from "./usageUtils";

describe("usageUtils", () => {
  it("formats compact numbers and usd", () => {
    expect(formatCompactNumber(456700)).toBe("456.7K");
    expect(formatUsd(0.004)).toBe("$0.0040");
  });

  it("formats short dates", () => {
    expect(formatShortDate("2026-05-30")).toMatch(/May|5/);
  });

  it("computes daily bar values", () => {
    const day = {
      date: "2026-05-30",
      input_tokens: 100,
      output_tokens: 50,
      total_tokens: 150,
      cost_usd: 0.01,
      cost_display: 0.08,
      llm_calls: 1,
    };
    expect(dailyBarValue(day, "tokens", "total")).toBe(150);
    expect(dailyBarValue(day, "tokens", "byType")).toBe(150);
    expect(dailyBarValue(day, "cost", "total")).toBe(0.08);
    expect(maxDailyBarValue([day], "tokens", "total")).toBe(150);
    expect(typeShare({ input_tokens: 75, output_tokens: 25, total_tokens: 100, cost_usd: 0, llm_calls: 1, tool_calls: 0, session_count: 1 }, "input_tokens")).toBe(0.75);
  });

  it("formats display currency and active dimensions", () => {
    expect(formatCost(1.38, 10, "¥", "CNY")).toBe("¥10.00");
    expect(formatCost(1.38, 10, "¥", "USD")).toBe("$1.38");
    expect(
      activeUsageDimensions({ cache_read: 100, reasoning: 20, input: 0 })
    ).toEqual([
      { key: "cache_read", value: 100 },
      { key: "reasoning", value: 20 },
    ]);
  });
});
