import type { LiveTurnState } from "./liveTurnReducer";
import { MarkdownView } from "../../lib/MarkdownView";
import { useI18n } from "../../lib/i18n";
import { useChatDisplay } from "../chat/chatDisplayPreferences";
import { isLiveTurnVisible } from "../../lib/messageVisibility";
import { ToolCardRow } from "../chat/ToolCardRow";
import { ChatBubbleShell } from "../chat/ChatBubbleShell";
import { MessageMetaDetails } from "../chat/MessageMetaDetails";
import type { ContextSnapshot } from "../../lib/schemas";
import { ThinkingBlock } from "./ThinkingBlock";
import { ChildAgentRunCard } from "./ChildAgentRunCard";

type AssistantTurnCardProps = {
  turn: LiveTurnState;
  agentName?: string;
  agentAvatar?: string;
  contextSnapshot?: ContextSnapshot | null;
  modelLabel?: string | null;
};

export function AssistantTurnCard({
  turn,
  agentName = "HarnessLab",
  agentAvatar = "HL",
  contextSnapshot,
  modelLabel,
}: AssistantTurnCardProps) {
  const { t } = useI18n();
  const { activityDisplay, showThinking, showTools } = useChatDisplay();
  const showThinkingPlaceholder =
    showThinking &&
    turn.phase === "running" &&
    turn.thinkingLikely &&
    turn.thoughts.every((item) => item.status !== "thinking") &&
    turn.thoughts.length === 0;

  const statusLabel =
    turn.phase === "running" || turn.phase === "pending"
      ? t("chat.working")
      : turn.phase === "stopped"
        ? t("chat.stopped")
        : null;

  if (!isLiveTurnVisible(turn, { showThinking, showTools })) {
    return null;
  }

  return (
    <ChatBubbleShell
      role="assistant"
      displayName={agentName}
      avatar={agentAvatar}
      createdAt={turn.userMessage.created_at}
      busy={turn.phase === "running" || turn.phase === "pending"}
      statusLabel={statusLabel}
      footerExtra={<MessageMetaDetails snapshot={contextSnapshot} modelLabel={modelLabel} />}
    >
      {showThinkingPlaceholder ? (
        <div
          className={`thinking-block thinking-block-active${activityDisplay === "compact" ? " thinking-block-compact" : ""}`}
          aria-live="polite"
        >
          <span className="thinking-pulse" aria-hidden />
          Thinking…
        </div>
      ) : null}

      {showThinking
        ? turn.thoughts.map((thought, idx) => (
            <ThinkingBlock
              key={`${thought.stepIndex}-${idx}`}
              thought={thought}
              displayMode={activityDisplay}
            />
          ))
        : null}

      {showTools && turn.tools.length > 0 ? (
        <div className="chat-msg-tools">
          {turn.tools.map((card, idx) => (
            <ToolCardRow
              key={`${card.tool}-${idx}`}
              card={card}
              displayMode={activityDisplay}
              defaultOpen={activityDisplay === "detailed" && idx === turn.tools.length - 1}
            />
          ))}
        </div>
      ) : null}

      {turn.childRuns.length > 0 ? (
        <div className="child-agent-runs">
          {turn.childRuns.map((run) => (
            <ChildAgentRunCard key={run.childSessionId} run={run} />
          ))}
        </div>
      ) : null}

      {turn.assistantText ? (
        <MarkdownView markdown={turn.assistantText} className="chat-msg-content" />
      ) : turn.phase === "running" || turn.phase === "pending" ? (
        <div className="assistant-turn-activity" aria-live="polite">
          {turn.tools.length === 0 && !turn.thinkingLikely && turn.thoughts.length === 0
            ? t("chat.runningStep")
            : null}
        </div>
      ) : null}
    </ChatBubbleShell>
  );
}
