import { describe, expect, it } from "vitest";
import type { SpanRecordItem } from "./schemas";
import { spanResourceRows, spanServiceName } from "./spanResource";

function sampleSpan(overrides: Partial<SpanRecordItem> = {}): SpanRecordItem {
  return {
    trace_id: "t1",
    span_id: "s1",
    name: "tool.read_file",
    session_id: "sess",
    turn_index: 0,
    start_time: "2026-01-01T00:00:00.000Z",
    end_time: "2026-01-01T00:00:01.000Z",
    duration_ms: 1000,
    attributes: {},
    ...overrides,
  };
}

describe("spanServiceName", () => {
  it("reads service.name from resource", () => {
    expect(
      spanServiceName(
        sampleSpan({
          resource: { "service.name": "harnesslab", "deployment.environment": "local" },
        })
      )
    ).toBe("harnesslab");
  });

  it("falls back to harnesslab when resource missing", () => {
    expect(spanServiceName(sampleSpan())).toBe("harnesslab");
  });
});

describe("spanResourceRows", () => {
  it("returns sorted resource key/value pairs", () => {
    const rows = spanResourceRows(
      sampleSpan({
        resource: {
          "service.name": "harnesslab",
          "service.version": "0.1.0",
          "deployment.environment": "local",
        },
      })
    );
    expect(rows.map(([k]) => k)).toEqual([
      "deployment.environment",
      "service.name",
      "service.version",
    ]);
  });

  it("falls back to service.name when resource missing", () => {
    expect(spanResourceRows(sampleSpan())).toEqual([["service.name", "harnesslab"]]);
  });
});
