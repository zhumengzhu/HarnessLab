import type {
  MessageItem,
  SessionDetailResponse,
  SessionSummary,
  ToolCard,
  TraceEventItem,
} from "../../lib/schemas";
import { TracePanel } from "../trace/TracePanel";

type SessionWorkspaceProps = {
  uiMode: "simple" | "advanced";
  selectedSessionId: string | null;
  sending: boolean;
  sessionActionError: string | null;
  sessionsLoading: boolean;
  sessionsError: string | null;
  sessionsRows: SessionSummary[];
  sessionDetailLoading: boolean;
  sessionDetailError: string | null;
  sessionDetailData?: SessionDetailResponse;
  sessionTraceLoading: boolean;
  sessionTraceError: string | null;
  traceRows: TraceEventItem[];
  visibleMessages: MessageItem[];
  toolMessages: MessageItem[];
  streamToolCards: ToolCard[];
  budgetEvents: TraceEventItem[];
  hasStreamTrace: boolean;
  onSelectSession: (id: string | null) => void;
  onForkCurrentSession: () => void;
  onClearStreamTrace: () => void;
};

export function SessionWorkspace(props: SessionWorkspaceProps) {
  const {
    uiMode,
    selectedSessionId,
    sending,
    sessionActionError,
    sessionsLoading,
    sessionsError,
    sessionsRows,
    sessionDetailLoading,
    sessionDetailError,
    sessionDetailData,
    sessionTraceLoading,
    sessionTraceError,
    traceRows,
    visibleMessages,
    toolMessages,
    streamToolCards,
    budgetEvents,
    hasStreamTrace,
    onSelectSession,
    onForkCurrentSession,
    onClearStreamTrace,
  } = props;

  return (
    <section className={`layout ${uiMode === "simple" ? "layout-simple" : ""}`}>
      <aside className="panel">
        <h2>Sessions</h2>
        <div className="session-actions">
          <button type="button" onClick={() => onSelectSession(null)} disabled={sending}>
            新对话
          </button>
          <button
            type="button"
            onClick={onForkCurrentSession}
            disabled={!selectedSessionId || sending}
          >
            Fork 当前会话
          </button>
        </div>
        {sessionActionError ? <p className="error-text">{sessionActionError}</p> : null}
        {sessionsLoading ? <p>Loading...</p> : null}
        {sessionsError ? <p>Failed: {sessionsError}</p> : null}
        <ul className="list">
          {sessionsRows.map((s) => (
            <li key={s.id}>
              <button
                className={selectedSessionId === s.id ? "active" : ""}
                onClick={() => onSelectSession(s.id)}
                type="button"
              >
                <strong>{s.title || s.goal}</strong>
                <small>{s.status} · {s.message_count} msgs</small>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="panel">
        <h2>{uiMode === "simple" ? "Chat" : "Session Detail"}</h2>
        {!selectedSessionId ? <p>{uiMode === "simple" ? "点击左侧“新对话”开始。" : "Select a session."}</p> : null}
        {sessionDetailLoading ? <p>Loading session...</p> : null}
        {sessionDetailError ? <p>Failed: {sessionDetailError}</p> : null}
        {selectedSessionId && sessionDetailData ? (
          <>
            {uiMode === "advanced" ? (
              <pre className="meta-block">{JSON.stringify(sessionDetailData.session, null, 2)}</pre>
            ) : null}
            {uiMode === "advanced" && sessionDetailData.session.memory_notes ? (
              <div className="memory-box">
                <h3>Memory Notes</h3>
                <pre>{sessionDetailData.session.memory_notes}</pre>
              </div>
            ) : null}
            {uiMode === "advanced" && sessionDetailData.session.budget_usage ? (
              <div className="budget-box">
                <h3>Budget Usage</h3>
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
                    <h4>Budget Events</h4>
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
            ) : null}
            <div className="messages">
              {visibleMessages.map((m) => (
                <div key={m.id} className={`msg ${m.role}`}>
                  <span className="role">{m.role}</span>
                  <pre>{m.content}</pre>
                </div>
              ))}
            </div>
            {uiMode === "advanced" && toolMessages.length ? (
              <div className="tool-cards">
                <h3>Tool Messages</h3>
                {toolMessages.map((m) => (
                  <div key={m.id} className="tool-card">
                    <strong>{toolNameFromContent(m.content)}</strong>
                    <pre>{m.content}</pre>
                  </div>
                ))}
              </div>
            ) : null}
            {uiMode === "advanced" && streamToolCards.length ? (
              <div className="tool-cards">
                <h3>Tool Cards (stream)</h3>
                {streamToolCards.map((c, idx) => (
                  <div key={`${c.tool}-${idx}`} className="tool-card">
                    <strong>
                      {c.tool || "tool"} · {c.ok ? "ok" : "error"}
                    </strong>
                    <pre>{c.error || c.output_preview || ""}</pre>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      {uiMode === "advanced" ? (
        <TracePanel
          selectedSessionId={selectedSessionId}
          loading={sessionTraceLoading}
          error={sessionTraceError}
          rows={traceRows}
          hasStreamTrace={hasStreamTrace}
          onClearStreamTrace={onClearStreamTrace}
        />
      ) : null}
    </section>
  );
}

function toolNameFromContent(content: string): string {
  const text = content.trim();
  if (!text.startsWith("[tool:")) return "tool";
  const end = text.indexOf("]");
  if (end <= 6) return "tool";
  return text.slice(6, end) || "tool";
}

