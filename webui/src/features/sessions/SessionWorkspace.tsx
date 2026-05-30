import { useMemo } from "react";
import type {
  MessageItem,
  SessionDetailResponse,
  TraceEventItem,
} from "../../lib/schemas";
import type { TurnEnrichment } from "../../lib/turnEnrichments";
import { AssistantTurnCard } from "../live-turn/AssistantTurnCard";
import type { LiveTurnState } from "../live-turn/liveTurnReducer";
import { ChatMessage } from "../chat/ChatMessage";
import { ChatScrollArea } from "../chat/ChatScrollArea";

type SessionWorkspaceProps = {
  uiMode: "simple" | "advanced";
  selectedSessionId: string | null;
  sending: boolean;
  sessionDetailLoading: boolean;
  sessionDetailError: string | null;
  sessionDetailData?: SessionDetailResponse;
  visibleMessages: MessageItem[];
  toolMessages: MessageItem[];
  turnEnrichments: Record<string, TurnEnrichment>;
  liveTurn: LiveTurnState | null;
  budgetEvents: TraceEventItem[];
  hasStreamMessages: boolean;
  onComposerChromeChange?: (collapsed: boolean) => void;
};

export function SessionWorkspace(props: SessionWorkspaceProps) {
  const {
    uiMode,
    selectedSessionId,
    sessionDetailLoading,
    sessionDetailError,
    sessionDetailData,
    visibleMessages,
    toolMessages,
    turnEnrichments,
    liveTurn,
    budgetEvents,
    hasStreamMessages,
    onComposerChromeChange,
  } = props;

  const showChat =
    liveTurn !== null ||
    visibleMessages.length > 0 ||
    (selectedSessionId !== null && sessionDetailData !== undefined);

  const chatScrollSignal = useMemo(() => {
    const last = visibleMessages.at(-1);
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
      {!selectedSessionId && !liveTurn && !hasStreamMessages ? (
        <p className="chat-empty-hint">点击侧栏「+ 新对话」开始，或从左侧选择历史会话。</p>
      ) : null}
      {sessionDetailLoading && selectedSessionId ? <p>Loading session…</p> : null}
      {sessionDetailError ? <p className="error-text">Failed: {sessionDetailError}</p> : null}

      {showChat ? (
        <>
          {uiMode === "advanced" && sessionDetailData ? (
            <details className="diag-block">
              <summary>Session metadata</summary>
              <pre className="meta-block">{JSON.stringify(sessionDetailData.session, null, 2)}</pre>
            </details>
          ) : null}

          {uiMode === "advanced" && sessionDetailData?.session.memory_notes ? (
            <details className="diag-block">
              <summary>Memory notes</summary>
              <pre>{sessionDetailData.session.memory_notes}</pre>
            </details>
          ) : null}

          {uiMode === "advanced" && sessionDetailData?.session.budget_usage ? (
            <details className="diag-block">
              <summary>Budget usage</summary>
              <div className="budget-box">
                <div className="budget-grid">
                  <span>LLM calls</span>
                  <strong>{sessionDetailData.session.budget_usage.llm_calls_total}</strong>
                  <span>Tool calls</span>
                  <strong>{sessionDetailData.session.budget_usage.tool_calls_total}</strong>
                  <span>Tokens</span>
                  <strong>{sessionDetailData.session.budget_usage.tokens_total}</strong>
                  <span>Wall time (ms)</span>
                  <strong>{sessionDetailData.session.budget_usage.wall_time_ms_total}</strong>
                  <span>Cost (USD)</span>
                  <strong>{sessionDetailData.session.budget_usage.cost_usd_total.toFixed(6)}</strong>
                  <span>Status</span>
                  <strong>{sessionDetailData.session.budget_usage.last_budget_status}</strong>
                </div>
                {budgetEvents.length ? (
                  <div className="budget-events">
                    <h4>Budget events</h4>
                    <ul>
                      {budgetEvents.map((evt) => (
                        <li key={`${evt.created_at}-${evt.event_type}`}>
                          <strong>{evt.event_type}</strong>
                          <span>{new Date(evt.created_at).toLocaleString()}</span>
                          <code>{JSON.stringify(evt.payload)}</code>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            </details>
          ) : null}

          <ChatScrollArea
            scrollSignal={chatScrollSignal}
            onComposerChromeChange={onComposerChromeChange}
          >
            <div className="messages">
              {visibleMessages.map((m) => {
                const enrichment = turnEnrichments[m.id];
                return (
                  <ChatMessage
                    key={m.id}
                    message={m}
                    toolCards={enrichment?.tools}
                    thoughtEntries={enrichment?.thoughts}
                  />
                );
              })}
              {liveTurn ? <AssistantTurnCard turn={liveTurn} /> : null}
            </div>
          </ChatScrollArea>

          {uiMode === "advanced" && toolMessages.length ? (
            <div className="tool-cards">
              <h3>Tool messages</h3>
              {toolMessages.map((m) => (
                <ChatMessage key={m.id} message={m} defaultCollapsed />
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
