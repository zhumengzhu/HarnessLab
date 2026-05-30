import { describe, expect, it } from "vitest";
import type { SpanRecordItem, SpanStartedPayload } from "../../lib/schemas";
import { createLiveTurn } from "./liveTurnReducer";
import { reduceLiveTurnSpan, type LiveSpanSignal } from "./liveTurnSpanReducer";

function started(
  payload: Partial<SpanStartedPayload> & Pick<SpanStartedPayload, "name">
): LiveSpanSignal {
  return {
    kind: "started",
    payload: {
      trace_id: "t1",
      span_id: `start-${payload.name}`,
      session_id: "s1",
      ...payload,
    },
  };
}

function completed(
  overrides: Partial<SpanRecordItem> & Pick<SpanRecordItem, "name">
): LiveSpanSignal {
  const now = new Date().toISOString();
  return {
    kind: "completed",
    record: {
      trace_id: "t1",
      span_id: `done-${overrides.name}`,
      session_id: "s1",
      turn_index: 0,
      start_time: now,
      end_time: now,
      duration_ms: 100,
      attributes: {},
      ...overrides,
    },
  };
}

describe("liveTurnSpanReducer", () => {
  it("creates optimistic user message", () => {
    const turn = createLiveTurn("hello");
    expect(turn.userMessage.role).toBe("user");
    expect(turn.userMessage.content).toBe("hello");
    expect(turn.phase).toBe("pending");
  });

  it("tracks thinking then thought on llm.generate", () => {
    let turn = createLiveTurn("hi");
    turn = reduceLiveTurnSpan(
      turn,
      started({
        name: "llm.generate",
        attributes: { "harnesslab.step.index": 0, "harnesslab.thinking.enabled": true },
      })
    )!;
    expect(turn.thoughts).toHaveLength(1);
    expect(turn.thoughts[0].status).toBe("thinking");

    turn = reduceLiveTurnSpan(
      turn,
      completed({
        name: "llm.generate",
        attributes: { "harnesslab.step.index": 0 },
        metrics: { latency_ms: 1200, reasoning_text: "Let me think…" },
      })
    )!;
    expect(turn.thoughts[0].status).toBe("done");
    expect(turn.thoughts[0].text).toBe("Let me think…");
    expect(turn.thoughts[0].durationMs).toBe(1200);
  });

  it("appends tool cards from completed tool spans", () => {
    let turn = createLiveTurn("run tool");
    turn = reduceLiveTurnSpan(
      turn,
      completed({
        name: "tool.read_file",
        attributes: {
          "harnesslab.tool.name": "read_file",
          "harnesslab.tool.ok": true,
        },
        metrics: {
          output_preview: "file contents",
          duration_ms: 42,
        },
      })
    )!;
    expect(turn.tools).toHaveLength(1);
    expect(turn.tools[0].tool).toBe("read_file");
  });

  it("tracks child agent progress from span link and child tool spans", () => {
    let turn = createLiveTurn("delegate");
    turn = reduceLiveTurnSpan(turn, {
      kind: "link",
      payload: {
        trace_id: "t1",
        span_id: "sub1",
        linked_trace_id: "t2",
        linked_span_id: "child-turn",
        attributes: {
          "harnesslab.child_session.id": "ses_child",
          "harnesslab.sub_agent.goal": "research topic",
        },
      },
    })!;
    expect(turn.childRuns).toHaveLength(1);
    expect(turn.childRuns[0].goal).toBe("research topic");

    turn = reduceLiveTurnSpan(
      turn,
      completed({
        name: "tool.read_file",
        child_session_id: "ses_child",
        attributes: {
          "harnesslab.tool.name": "read_file",
          "harnesslab.tool.ok": true,
        },
        metrics: { output_preview: "notes" },
      })
    )!;
    expect(turn.childRuns[0].tools).toHaveLength(1);
    expect(turn.childRuns[0].tools[0].tool).toBe("read_file");
  });

  it("sets assistant text on decision.applied span event", () => {
    let turn = createLiveTurn("question");
    turn = reduceLiveTurnSpan(
      turn,
      started({
        name: "llm.generate",
        attributes: { "harnesslab.step.index": 0, "harnesslab.thinking.enabled": true },
      })
    )!;
    turn = reduceLiveTurnSpan(
      turn,
      completed({
        name: "llm.generate",
        attributes: { "harnesslab.step.index": 0 },
        metrics: { latency_ms: 900, reasoning_text: "plan answer" },
      })
    )!;
    turn = reduceLiveTurnSpan(turn, {
      kind: "event",
      payload: {
        trace_id: "t1",
        span_id: "llm1",
        name: "decision.applied",
        attributes: {
          kind: "final",
          assistant_message: "Here is the answer.",
        },
      },
    })!;
    expect(turn.phase).toBe("answering");
    expect(turn.assistantText).toBe("Here is the answer.");
    expect(turn.thoughts).toHaveLength(1);
    expect(turn.thoughts[0].text).toBe("plan answer");
  });
});
