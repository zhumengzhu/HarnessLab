import { describe, expect, it } from "vitest";
import { buildTraceSpanTree, flattenTraceSpanTree } from "./buildTraceSpanTree";
import type { TraceEventItem } from "../../lib/schemas";

function evt(
  eventType: string,
  payload: Record<string, unknown>,
  createdAt: string
): TraceEventItem {
  return {
    run_id: "run_1",
    session_id: "ses_1",
    event_type: eventType,
    payload,
    created_at: createdAt,
  };
}

describe("buildTraceSpanTree", () => {
  it("builds turn and tool spans from flat events", () => {
    const tree = buildTraceSpanTree([
      evt("session_started", { goal: "demo" }, "2026-01-01T00:00:00.000Z"),
      evt("user_input_received", { turn_index: 0, user_input: "hello" }, "2026-01-01T00:00:01.000Z"),
      evt(
        "tool_denied",
        { tool: "run_shell_safe", reason: "deny" },
        "2026-01-01T00:00:01.100Z"
      ),
    ]);

    expect(tree?.name).toBe("demo");
    expect(tree?.children).toHaveLength(1);
    expect(tree?.children[0]?.kind).toBe("turn");
    expect(tree?.children[0]?.children[0]?.kind).toBe("tool");
    expect(tree?.children[0]?.children[0]?.status).toBe("error");
  });

  it("pairs step and model_call spans", () => {
    const tree = buildTraceSpanTree([
      evt("session_started", { goal: "x" }, "2026-01-01T00:00:00.000Z"),
      evt("user_input_received", { turn_index: 0, user_input: "hi" }, "2026-01-01T00:00:01.000Z"),
      evt("step_started", { step_index: 0 }, "2026-01-01T00:00:01.010Z"),
      evt("model_call_started", { step_index: 0 }, "2026-01-01T00:00:01.020Z"),
      evt(
        "model_call",
        { decision_kind: "final", latency_ms: 42 },
        "2026-01-01T00:00:01.070Z"
      ),
      evt("step_completed", { step_index: 0, outcome: "final" }, "2026-01-01T00:00:01.080Z"),
    ]);

    const flat = flattenTraceSpanTree(tree!);
    const kinds = flat.map((n) => n.kind);
    expect(kinds).toContain("step");
    expect(kinds).toContain("model");
    const model = flat.find((n) => n.kind === "model");
    expect(model?.durationMs).toBe(42);
    expect(model?.name).toContain("final");
  });

  it("returns null for empty input", () => {
    expect(buildTraceSpanTree([])).toBeNull();
  });
});
