import { useMemo } from "react";
import type { MessageItem, ToolCard, ContextSnapshot } from "../../lib/schemas";
import { MarkdownView } from "../../lib/MarkdownView";
import { useI18n } from "../../lib/i18n";
import { useChatDisplay } from "./chatDisplayPreferences";
import { ToolCardRow } from "./ToolCardRow";
import { ThinkingBlock } from "../live-turn/ThinkingBlock";
import type { ThoughtEntry } from "../live-turn/liveTurnReducer";
import { ChatBubbleShell } from "./ChatBubbleShell";
import { MessageMetaDetails } from "./MessageMetaDetails";
import {
  assistantDisplayBody,
  isChatMessageVisible,
  resolvePersistedThoughts,
} from "../../lib/messageVisibility";

type ChatMessageProps = {
  message: MessageItem;
  toolCards?: ToolCard[];
  thoughtEntries?: ThoughtEntry[];
  agentName?: string;
  agentAvatar?: string;
  contextSnapshot?: ContextSnapshot | null;
  showContextMeta?: boolean;
  modelLabel?: string | null;
};

function MessageBody({
  displayBody,
  persistedThoughts,
  toolCards,
  activityDisplay,
  showThinking,
  showTools,
}: {
  displayBody: string;
  persistedThoughts: ThoughtEntry[];
  toolCards: ToolCard[];
  activityDisplay: "compact" | "detailed";
  showThinking: boolean;
  showTools: boolean;
}) {
  return (
    <>
      {showThinking
        ? persistedThoughts.map((thought, idx) => (
            <ThinkingBlock
              key={idx}
              thought={thought}
              showWhenIdle
              displayMode={activityDisplay}
            />
          ))
        : null}

      {showTools && toolCards.length > 0 ? (
        <div className="chat-msg-tools">
          {toolCards.map((card, idx) => (
            <ToolCardRow key={`${card.tool}-${idx}`} card={card} displayMode={activityDisplay} />
          ))}
        </div>
      ) : null}

      {displayBody ? <MarkdownView markdown={displayBody} className="chat-msg-content" /> : null}
    </>
  );
}

export function ChatMessage({
  message,
  toolCards = [],
  thoughtEntries,
  agentName = "HarnessLab",
  agentAvatar = "HL",
  contextSnapshot,
  showContextMeta = false,
  modelLabel,
}: ChatMessageProps) {
  const { t } = useI18n();
  const { activityDisplay, showThinking, showTools } = useChatDisplay();

  const persistedThoughts = useMemo(
    () => resolvePersistedThoughts(message, thoughtEntries),
    [message, thoughtEntries]
  );

  const displayBody = useMemo(() => {
    if (message.role === "assistant") {
      return assistantDisplayBody(message);
    }
    return message.content.trim();
  }, [message]);

  const visible = isChatMessageVisible(
    message,
    { showThinking, showTools },
    { thoughts: persistedThoughts, tools: toolCards }
  );

  const bodyProps = {
    displayBody,
    persistedThoughts,
    toolCards,
    activityDisplay,
    showThinking,
    showTools,
  };

  if (!visible) {
    return null;
  }

  if (message.role === "user") {
    return (
      <ChatBubbleShell
        role="user"
        displayName={t("chat.you")}
        avatar="Y"
        createdAt={message.created_at}
      >
        <MessageBody {...bodyProps} />
      </ChatBubbleShell>
    );
  }

  if (message.role === "assistant") {
    return (
      <ChatBubbleShell
        role="assistant"
        displayName={agentName}
        avatar={agentAvatar}
        createdAt={message.created_at}
        footerExtra={
          showContextMeta ? (
            <MessageMetaDetails snapshot={contextSnapshot} modelLabel={modelLabel} />
          ) : undefined
        }
      >
        <MessageBody {...bodyProps} />
      </ChatBubbleShell>
    );
  }

  return (
    <article className={`chat-msg chat-msg-${message.role} chat-msg-system`}>
      <div className="chat-msg-header chat-msg-header-static">
        <span className="chat-msg-role">{t("chat.tool")}</span>
      </div>
      <div className="chat-msg-body">
        <MessageBody {...bodyProps} />
      </div>
    </article>
  );
}
