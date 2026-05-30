import { describe, expect, it } from "vitest";
import {
  createLiveTurn,
  reduceLiveTurn,
} from "./liveTurnReducer";
import type { TraceEventItem } from "../../lib/schemas";

function traceEvt(
  event_type: string,
  payload: Record<string, unknown>
): TraceEventItem {
  return {
    run_id: "r1",
    session_id: "s1",
    event_type,
    payload,
    created_at: new Date().toISOString(),
  };
}

describe("liveTurnReducer", () => {
  it("creates optimistic user message", () => {
    const turn = createLiveTurn("hello");
    expect(turn.userMessage.role).toBe("user");
    expect(turn.userMessage.content).toBe("hello");
    expect(turn.phase).toBe("pending");
  });

  it("tracks thinking then thought on model_call", () => {
    let turn = createLiveTurn("hi");
    turn = reduceLiveTurn(turn, traceEvt("model_call_started", { step_index: 0, thinking_likely: true }))!;
    expect(turn.thoughts).toHaveLength(1);
    expect(turn.thoughts[0].status).toBe("thinking");

    turn = reduceLiveTurn(
      turn,
      traceEvt("model_call", {
        latency_ms: 1200,
        reasoning_text: "Let me think…",
      })
    )!;
    expect(turn.thoughts[0].status).toBe("done");
    expect(turn.thoughts[0].text).toBe("Let me think…");
    expect(turn.thoughts[0].durationMs).toBe(1200);
  });

  it("appends tool cards from tool_executed", () => {
    let turn = createLiveTurn("run tool");
    turn = reduceLiveTurn(
      turn,
      traceEvt("tool_executed", {
        tool: "read_file",
        ok: true,
        output_preview: "file contents",
        duration_ms: 42,
      })
    )!;
    expect(turn.tools).toHaveLength(1);
    expect(turn.tools[0].tool).toBe("read_file");
  });

  it("tracks child agent progress from spawned SSE events", () => {
    let turn = createLiveTurn("delegate");
    turn = reduceLiveTurn(
      turn,
      traceEvt("sub_agent_spawned", {
        child_session_id: "ses_child",
        goal: "research topic",
        max_steps: 2,
      })
    )!;
    expect(turn.childRuns).toHaveLength(1);
    expect(turn.childRuns[0].goal).toBe("research topic");

    turn = reduceLiveTurn(
      turn,
      {
        ...traceEvt("tool_executed", {
          tool: "read_file",
          ok: true,
          output_preview: "notes",
        }),
        child_session_id: "ses_child",
      }
    )!;
    expect(turn.childRuns[0].tools).toHaveLength(1);
    expect(turn.childRuns[0].tools[0].tool).toBe("read_file");
  });

  it("sets assistant text on final decision without duplicating model reasoning", () => {
    let turn = createLiveTurn("question");
    turn = reduceLiveTurn(
      turn,
      traceEvt("model_call", {
        latency_ms: 900,
        reasoning_text: "plan answer",
      })
    )!;
    turn = reduceLiveTurn(
      turn,
      traceEvt("decision_made", {
        kind: "final",
        assistant_message: "Here is the answer.",
        reasoning_text: "plan answer",
      })
    )!;
    expect(turn.phase).toBe("answering");
    expect(turn.assistantText).toBe("Here is the answer.");
    expect(turn.thoughts).toHaveLength(1);
    expect(turn.thoughts[0].text).toBe("plan answer");
  });
});
