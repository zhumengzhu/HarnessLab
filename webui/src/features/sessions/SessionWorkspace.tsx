import { useMemo } from "react";
import { ChatScrollArea } from "../chat/ChatScrollArea";
import { ChatMessage } from "../chat/ChatMessage";
import { ChatEmptyHero } from "../chat/ChatEmptyHero";
import { AssistantTurnCard } from "../live-turn/AssistantTurnCard";
import type { LiveTurnState } from "../live-turn/liveTurnReducer";
import type { ContextSnapshot, MessageItem, SessionDetailResponse } from "../../lib/schemas";
import type { TurnEnrichment } from "../../lib/turnEnrichments";
import type { AgentPersona } from "../../lib/agentPersona";
import { useI18n } from "../../lib/i18n";

type SessionWorkspaceProps = {
  selectedSessionId: string | null;
  sessionDetailLoading: boolean;
  sessionDetailError: string | null;
  sessionDetailData?: SessionDetailResponse;
  visibleMessages: MessageItem[];
  turnEnrichments: Record<string, TurnEnrichment>;
  liveTurn: LiveTurnState | null;
  hasStreamMessages: boolean;
  persona: AgentPersona;
  contextSnapshot?: ContextSnapshot | null;
  modelLabel?: string | null;
  onPickPrompt: (text: string) => void;
  onComposerChromeChange?: (collapsed: boolean) => void;
};

export function SessionWorkspace(props: SessionWorkspaceProps) {
  const {
    selectedSessionId,
    sessionDetailLoading,
    sessionDetailError,
    sessionDetailData,
    visibleMessages,
    turnEnrichments,
    liveTurn,
    hasStreamMessages,
    persona,
    contextSnapshot,
    modelLabel,
    onPickPrompt,
    onComposerChromeChange,
  } = props;
  const { t } = useI18n();

  const isEmpty =
    !liveTurn &&
    visibleMessages.length === 0 &&
    !hasStreamMessages &&
    (selectedSessionId === null || sessionDetailData !== undefined);

  const lastAssistantMessageId = useMemo(() => {
    for (let index = visibleMessages.length - 1; index >= 0; index -= 1) {
      if (visibleMessages[index]?.role === "assistant") {
        return visibleMessages[index]?.id ?? null;
      }
    }
    return null;
  }, [visibleMessages]);

  const chatScrollSignal = useMemo(() => {
    const last = visibleMessages.length ? visibleMessages[visibleMessages.length - 1] : undefined;
    return [
      visibleMessages.length,
      last?.id ?? "",
      last?.content.length ?? 0,
      liveTurn?.userMessage.id ?? "",
      liveTurn?.assistantText.length ?? 0,
      liveTurn?.thoughts.length ?? 0,
      liveTurn?.tools.length ?? 0,
    ].join("|");
  }, [visibleMessages, liveTurn]);

  return (
    <section className="chat-panel">
      {sessionDetailLoading && selectedSessionId ? (
        <p className="chat-panel-status">{t("chat.loadingSession")}</p>
      ) : null}
      {sessionDetailError ? (
        <p className="error-text">{t("common.loadFailed", { error: sessionDetailError })}</p>
      ) : null}

      <ChatScrollArea
        scrollSignal={chatScrollSignal}
        resetKey={selectedSessionId}
        onComposerChromeChange={onComposerChromeChange}
      >
        {isEmpty ? (
          <ChatEmptyHero persona={persona} onPickPrompt={onPickPrompt} />
        ) : (
          <div className="messages chat-thread">
            {visibleMessages.map((message) => {
              const enrichment = turnEnrichments[message.id];
              return (
                <ChatMessage
                  key={message.id}
                  message={message}
                  toolCards={enrichment?.tools}
                  thoughtEntries={enrichment?.thoughts}
                  agentName={persona.name}
                  agentAvatar={persona.avatar}
                  contextSnapshot={contextSnapshot}
                  showContextMeta={
                    !liveTurn && message.id === lastAssistantMessageId && message.role === "assistant"
                  }
                  modelLabel={modelLabel}
                />
              );
            })}
            {liveTurn ? (
              <AssistantTurnCard
                turn={liveTurn}
                agentName={persona.name}
                agentAvatar={persona.avatar}
                contextSnapshot={contextSnapshot}
                modelLabel={modelLabel}
              />
            ) : null}
          </div>
        )}
      </ChatScrollArea>
    </section>
  );
}
