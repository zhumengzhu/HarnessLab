import { describe, expect, it } from "vitest";
import {
  activityEntryFromSpanCompleted,
  activityEntryFromSpanStarted,
  buildActivityFeedFromSpans,
} from "./activityFeed";
import type { SpanRecordItem } from "../../lib/schemas";

function span(overrides: Partial<SpanRecordItem> & Pick<SpanRecordItem, "span_id" | "name">): SpanRecordItem {
  return {
    trace_id: "t1",
    session_id: "ses1",
    turn_index: 0,
    start_time: "2026-05-28T00:00:00Z",
    end_time: "2026-05-28T00:00:01Z",
    duration_ms: 1000,
    attributes: {},
    ...overrides,
  };
}

describe("activityFeed spans", () => {
  it("surfaces failover on llm.generate spans", () => {
    const entry = activityEntryFromSpanCompleted(
      span({
        span_id: "llm1",
        name: "llm.generate",
        attributes: { "harnesslab.failover.attempts": 2 },
      })
    );
    expect(entry?.kind).toBe("failover");
  });

  it("surfaces hook spans", () => {
    const entry = activityEntryFromSpanCompleted(
      span({
        span_id: "hook1",
        name: "tool.hooks.pre",
        attributes: {
          "harnesslab.hook.name": "block-rm",
          "harnesslab.hook.phase": "pre_tool",
          "harnesslab.hook.type": "prompt",
        },
      })
    );
    expect(entry?.kind).toBe("hook");
    expect(entry?.label).toContain("block-rm");
  });

  it("maps tool spans with redacted detail", () => {
    const entry = activityEntryFromSpanCompleted(
      span({
        span_id: "tool1",
        name: "tool.grep",
        attributes: {
          "harnesslab.tool.name": "grep",
          "harnesslab.tool.ok": true,
        },
        metrics: {
          duration_ms: 120,
          output_preview: "line one",
        },
      })
    );
    expect(entry?.label).toBe("grep · ok · 120ms");
    expect(entry?.detail).toContain("line one");
  });

  it("maps step started", () => {
    const entry = activityEntryFromSpanStarted({
      trace_id: "t1",
      span_id: "step1",
      name: "harnesslab.step",
      session_id: "ses1",
      attributes: { "harnesslab.step.index": 0 },
    });
    expect(entry?.kind).toBe("step");
  });

  it("builds newest-first feed with cap", () => {
    const feed = buildActivityFeedFromSpans(
      [
        span({
          span_id: "tool1",
          name: "tool.read_file",
          attributes: { "harnesslab.tool.name": "read_file", "harnesslab.tool.ok": true },
          end_time: "2026-05-28T00:00:01Z",
        }),
        span({
          span_id: "tool2",
          name: "tool.shell",
          attributes: {
            "harnesslab.tool.name": "shell",
            "harnesslab.tool.ok": false,
            "harnesslab.policy.decision": "deny:policy",
          },
          metrics: { error: "not allowed" },
          end_time: "2026-05-28T00:00:02Z",
        }),
      ],
      1
    );
    expect(feed).toHaveLength(1);
    expect(feed[0]?.kind).toBe("tool_denied");
  });
});
