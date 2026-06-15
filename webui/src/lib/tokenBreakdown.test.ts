import { describe, expect, it } from "vitest";
import { hasTokenBreakdown, tokenBreakdownRows } from "./tokenBreakdown";

describe("tokenBreakdownRows", () => {
  it("returns positive dimensions in canonical order", () => {
    const rows = tokenBreakdownRows({
      output: 120,
      cache_read: 300,
      input: 50,
      cache_write: 0,
    });
    expect(rows.map((row) => row.key)).toEqual(["input", "output", "cache_read"]);
    expect(rows[2]?.tokens).toBe(300);
  });

  it("detects empty breakdown", () => {
    expect(hasTokenBreakdown({})).toBe(false);
    expect(hasTokenBreakdown({ cache_read: 10 })).toBe(true);
  });
});
