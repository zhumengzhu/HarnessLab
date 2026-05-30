import type { ChildAgentRun } from "./liveTurnReducer";
import { MarkdownView } from "../../lib/MarkdownView";
import { useChatDisplay } from "../chat/chatDisplayPreferences";
import { ToolCardRow } from "../chat/ToolCardRow";
import { ThinkingBlock } from "./ThinkingBlock";

type ChildAgentRunCardProps = {
  run: ChildAgentRun;
};

export function ChildAgentRunCard({ run }: ChildAgentRunCardProps) {
  const { activityDisplay } = useChatDisplay();
  const busy = run.phase === "running" || run.phase === "pending";

  return (
    <article
      className={`child-agent-run child-agent-run-${run.phase}`}
      aria-busy={busy}
      aria-label={`子 Agent: ${run.goal}`}
    >
      <header className="child-agent-run-header">
        <span className="child-agent-run-label">子 Agent</span>
        <span className="child-agent-run-goal">{run.goal}</span>
        {busy ? <span className="child-agent-run-status">Running…</span> : null}
      </header>

      <div className="child-agent-run-body">
        {run.thoughts.map((thought, idx) => (
          <ThinkingBlock
            key={`${run.childSessionId}-${thought.stepIndex}-${idx}`}
            thought={thought}
            displayMode={activityDisplay}
          />
        ))}

        {run.tools.length > 0 ? (
          <div className="chat-msg-tools">
            {run.tools.map((card, idx) => (
              <ToolCardRow
                key={`${run.childSessionId}-tool-${idx}`}
                card={card}
                displayMode={activityDisplay}
              />
            ))}
          </div>
        ) : null}

        {run.assistantText ? (
          <MarkdownView markdown={run.assistantText} className="chat-msg-content" />
        ) : busy ? (
          <p className="child-agent-run-activity" aria-live="polite">
            子会话执行中…
          </p>
        ) : null}
      </div>
    </article>
  );
}
