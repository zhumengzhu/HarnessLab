import type { LiveTurnState } from "./liveTurnReducer";
import { MarkdownView } from "../../lib/MarkdownView";
import { ThinkingBlock } from "./ThinkingBlock";

type AssistantTurnCardProps = {
  turn: LiveTurnState;
};

export function AssistantTurnCard({ turn }: AssistantTurnCardProps) {
  const showThinkingPlaceholder =
    turn.phase === "running" &&
    turn.thinkingLikely &&
    turn.thoughts.every((t) => t.status !== "thinking") &&
    turn.thoughts.length === 0;

  return (
    <article
      className={`assistant-turn assistant-turn-${turn.phase}`}
      aria-busy={turn.phase === "running" || turn.phase === "pending"}
    >
      <header className="assistant-turn-header">
        <span className="chat-msg-role">Assistant</span>
        {turn.phase === "running" || turn.phase === "pending" ? (
          <span className="assistant-turn-status">Working…</span>
        ) : turn.phase === "stopped" ? (
          <span className="assistant-turn-status">Stopped</span>
        ) : null}
      </header>

      <div className="assistant-turn-body">
        {showThinkingPlaceholder ? (
          <div className="thinking-block thinking-block-active" aria-live="polite">
            <span className="thinking-pulse" aria-hidden />
            Thinking…
          </div>
        ) : null}

        {turn.thoughts.map((thought, idx) => (
          <ThinkingBlock key={`${thought.stepIndex}-${idx}`} thought={thought} />
        ))}

        {turn.tools.length > 0 ? (
          <div className="chat-msg-tools">
            {turn.tools.map((card, idx) => (
              <details key={`${card.tool}-${idx}`} className="chat-msg-tool" open={idx === turn.tools.length - 1}>
                <summary>
                  {card.tool || "tool"} · {card.ok ? "ok" : "error"}
                  {card.duration_ms != null ? ` · ${card.duration_ms}ms` : ""}
                </summary>
                <pre>{card.error || card.output_preview || ""}</pre>
              </details>
            ))}
          </div>
        ) : null}

        {turn.assistantText ? (
          <MarkdownView markdown={turn.assistantText} className="chat-msg-content" />
        ) : turn.phase === "running" || turn.phase === "pending" ? (
          <div className="assistant-turn-activity" aria-live="polite">
            {turn.tools.length === 0 && !turn.thinkingLikely && turn.thoughts.length === 0
              ? "Running agent step…"
              : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}
