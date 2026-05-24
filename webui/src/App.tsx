import { FormEvent, KeyboardEvent, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./lib/api-client";
import { postSse } from "./lib/sse-client";
import type {
  ForkResponse,
  HealthResponse,
  MessageItem,
  ProposalDetailResponse,
  ProposalsResponse,
  SessionDetailResponse,
  SessionsResponse,
  SettingsResponse,
  ToolCard,
  TurnPayload,
  TraceResponse,
} from "./lib/schemas";

export function App() {
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [composer, setComposer] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sessionActionError, setSessionActionError] = useState<string | null>(null);
  const [rememberMode, setRememberMode] = useState(false);
  const [skillMode, setSkillMode] = useState(false);
  const [streamTrace, setStreamTrace] = useState<TraceResponse["events"]>([]);
  const [streamToolCards, setStreamToolCards] = useState<ToolCard[]>([]);
  const [streamMessages, setStreamMessages] = useState<MessageItem[] | null>(null);

  function selectSession(id: string | null) {
    setSelectedSessionId(id);
    setSessionActionError(null);
    setRememberMode(false);
    setSkillMode(false);
    setStreamTrace([]);
    setStreamToolCards([]);
    setStreamMessages(null);
  }

  function prepareOutgoingText(text: string): string {
    const trimmed = text.trim();
    if (!trimmed) return "";
    if (rememberMode || trimmed.startsWith("/remember ")) {
      setRememberMode(false);
      if (trimmed.startsWith("/remember ")) return trimmed;
      return `/remember ${trimmed}`;
    }
    if (skillMode || trimmed.startsWith("/skill")) {
      setSkillMode(false);
      if (trimmed.startsWith("/skill")) return trimmed;
      return `/skill ${trimmed}`;
    }
    return trimmed;
  }

  async function forkCurrentSession() {
    if (!selectedSessionId || sending) return;
    setSessionActionError(null);
    try {
      const data = await apiPost<ForkResponse>(
        `/api/sessions/${encodeURIComponent(selectedSessionId)}/fork`,
        {}
      );
      selectSession(data.session.id);
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    } catch (err) {
      setSessionActionError((err as Error).message);
    }
  }

  function onComposerKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sending && composer.trim()) {
        e.currentTarget.form?.requestSubmit();
      }
    }
  }
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => apiGet<HealthResponse>("/api/health"),
  });
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGet<SettingsResponse>("/api/settings"),
  });
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () => apiGet<SessionsResponse>("/api/sessions?limit=50"),
  });
  const proposals = useQuery({
    queryKey: ["proposals"],
    queryFn: () => apiGet<ProposalsResponse>("/api/proposals?status=open"),
  });
  const sessionDetail = useQuery({
    queryKey: ["session", selectedSessionId],
    queryFn: () =>
      apiGet<SessionDetailResponse>(`/api/sessions/${encodeURIComponent(selectedSessionId || "")}`),
    enabled: Boolean(selectedSessionId),
  });
  const sessionTrace = useQuery({
    queryKey: ["trace", selectedSessionId],
    queryFn: () =>
      apiGet<TraceResponse>(`/api/sessions/${encodeURIComponent(selectedSessionId || "")}/trace`),
    enabled: Boolean(selectedSessionId),
  });
  const proposalDetail = useQuery({
    queryKey: ["proposal", selectedProposalId],
    queryFn: () =>
      apiGet<ProposalDetailResponse>(
        `/api/proposals/${encodeURIComponent(selectedProposalId || "")}`
      ),
    enabled: Boolean(selectedProposalId),
  });

  const visibleMessages = useMemo(() => {
    const rows = streamMessages ?? sessionDetail.data?.messages ?? [];
    return rows.filter((m) => m.role === "user" || (m.role === "assistant" && m.content.trim()));
  }, [sessionDetail.data?.messages, streamMessages]);
  const toolMessages = useMemo(() => {
    const rows = streamMessages ?? sessionDetail.data?.messages ?? [];
    return rows.filter((m) => m.role === "tool");
  }, [sessionDetail.data?.messages, streamMessages]);
  const traceRows = useMemo(() => {
    const base = sessionTrace.data?.events || [];
    return [...base, ...streamTrace];
  }, [sessionTrace.data?.events, streamTrace]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const outgoing = prepareOutgoingText(composer);
    if (!outgoing || sending) return;
    setSending(true);
    setSendError(null);
    setSessionActionError(null);
    setStreamTrace([]);
    setStreamToolCards([]);
    try {
      const path = selectedSessionId
        ? `/api/sessions/${encodeURIComponent(selectedSessionId)}/messages`
        : "/api/sessions";
      let donePayload: unknown = null;
      await postSse(
        path,
        { message: outgoing },
        {
          onTrace: (payload) => {
            setStreamTrace((prev) => [...prev, payload as TraceResponse["events"][number]]);
          },
          onDone: (payload) => {
            donePayload = payload as TurnPayload;
          },
          onError: (message) => {
            setSendError(message);
          },
        }
      );
      const finalPayload = toTurnPayload(donePayload);
      if (finalPayload) {
        selectSession(finalPayload.session.id);
        setStreamMessages(finalPayload.messages);
        setStreamToolCards(finalPayload.tool_cards || []);
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["sessions"] }),
          queryClient.invalidateQueries({ queryKey: ["session", finalPayload.session.id] }),
          queryClient.invalidateQueries({ queryKey: ["trace", finalPayload.session.id] }),
        ]);
      }
      setComposer("");
    } catch (err) {
      setSendError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="page">
      <header className="header">
        <div>
          <h1>HarnessLab TS UI (Phase C)</h1>
          <p>Interactive parity: composer, stream, remember/skill, fork.</p>
        </div>
        <div className="header-meta">
          <span>{health.data?.ok ? "health: ok" : "health: -"}</span>
          <span>model: {health.data?.model || "-"}</span>
        </div>
      </header>

      <section className="layout">
        <aside className="panel">
          <h2>Sessions</h2>
          <div className="session-actions">
            <button type="button" onClick={() => selectSession(null)} disabled={sending}>
              新对话
            </button>
            <button
              type="button"
              onClick={forkCurrentSession}
              disabled={!selectedSessionId || sending}
            >
              Fork 当前会话
            </button>
          </div>
          {sessionActionError ? <p className="error-text">{sessionActionError}</p> : null}
          {sessions.isLoading ? <p>Loading...</p> : null}
          {sessions.isError ? <p>Failed: {(sessions.error as Error).message}</p> : null}
          <ul className="list">
            {(sessions.data?.sessions || []).map((s) => (
              <li key={s.id}>
                <button
                  className={selectedSessionId === s.id ? "active" : ""}
                  onClick={() => selectSession(s.id)}
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
          <h2>Session Detail</h2>
          {!selectedSessionId ? <p>Select a session.</p> : null}
          {sessionDetail.isLoading ? <p>Loading session...</p> : null}
          {sessionDetail.isError ? <p>Failed: {(sessionDetail.error as Error).message}</p> : null}
          {selectedSessionId && sessionDetail.data ? (
            <>
              <pre className="meta-block">
{JSON.stringify(sessionDetail.data.session, null, 2)}
              </pre>
              {sessionDetail.data.session.memory_notes ? (
                <div className="memory-box">
                  <h3>Memory Notes</h3>
                  <pre>{sessionDetail.data.session.memory_notes}</pre>
                </div>
              ) : null}
              {sessionDetail.data.session.budget_usage ? (
                <div className="budget-box">
                  <h3>Budget Usage</h3>
                  <div className="budget-grid">
                    <span>LLM calls</span>
                    <strong>{sessionDetail.data.session.budget_usage.llm_calls_total}</strong>
                    <span>Tool calls</span>
                    <strong>{sessionDetail.data.session.budget_usage.tool_calls_total}</strong>
                    <span>Tokens</span>
                    <strong>{sessionDetail.data.session.budget_usage.tokens_total}</strong>
                    <span>Wall time (ms)</span>
                    <strong>{sessionDetail.data.session.budget_usage.wall_time_ms_total}</strong>
                    <span>Cost (USD)</span>
                    <strong>{sessionDetail.data.session.budget_usage.cost_usd_total.toFixed(6)}</strong>
                    <span>Status</span>
                    <strong>{sessionDetail.data.session.budget_usage.last_budget_status}</strong>
                  </div>
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
              {toolMessages.length ? (
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
              {streamToolCards.length ? (
                <div className="tool-cards">
                  <h3>Tool Cards (stream)</h3>
                  {streamToolCards.map((c, idx) => (
                    <div key={`${c.tool}-${idx}`} className="tool-card">
                      <strong>{c.tool || "tool"} · {c.ok ? "ok" : "error"}</strong>
                      <pre>{c.error || c.output_preview || ""}</pre>
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </section>

        <aside className="panel">
          <div className="panel-title-row">
            <h2>Trace</h2>
            <button
              type="button"
              onClick={() => setStreamTrace([])}
              disabled={!streamTrace.length}
            >
              清空实时流
            </button>
          </div>
          {!selectedSessionId ? <p>Select a session.</p> : null}
          {sessionTrace.isLoading ? <p>Loading trace...</p> : null}
          {sessionTrace.isError ? <p>Failed: {(sessionTrace.error as Error).message}</p> : null}
          <ul className="trace-list">
            {!traceRows.length ? <li>暂无事件</li> : null}
            {traceRows.map((e) => (
              <li key={`${e.created_at}-${e.event_type}`}>
                <strong>{e.event_type}</strong>
                <div className="trace-summary">{summarizeTraceEvent(e.event_type, e.payload)}</div>
                <pre>{JSON.stringify(e.payload, null, 2)}</pre>
              </li>
            ))}
          </ul>
        </aside>
      </section>

      <section className="layout-single">
        <section className="panel">
          <h2>Proposals (open)</h2>
          {proposals.isLoading ? <p>Loading...</p> : null}
          {proposals.isError ? <p>Failed: {(proposals.error as Error).message}</p> : null}
          <div className="proposal-grid">
            <ul className="list">
              {(proposals.data?.proposals || []).map((p) => (
                <li key={p.id}>
                  <button
                    className={selectedProposalId === p.id ? "active" : ""}
                    onClick={() => setSelectedProposalId(p.id)}
                    type="button"
                  >
                    <strong>{p.id}</strong>
                    <small>{p.kind} · {p.occurrences}</small>
                  </button>
                </li>
              ))}
            </ul>
            <div className="proposal-detail">
              {!selectedProposalId ? <p>Select a proposal.</p> : null}
              {proposalDetail.isLoading ? <p>Loading proposal...</p> : null}
              {proposalDetail.isError ? (
                <p>Failed: {(proposalDetail.error as Error).message}</p>
              ) : null}
              {proposalDetail.data ? (
                <>
                  <pre className="meta-block">
{JSON.stringify(
  {
    id: proposalDetail.data.proposal.id,
    status: proposalDetail.data.proposal.status,
    kind: proposalDetail.data.proposal.kind,
    occurrences: proposalDetail.data.proposal.occurrences,
    generated_at: proposalDetail.data.proposal.generated_at,
  },
  null,
  2
)}
                  </pre>
                  <MarkdownView markdown={proposalDetail.data.proposal.body_markdown} />
                </>
              ) : null}
            </div>
          </div>
        </section>
      </section>

      <section className="panel">
        <h2>Composer</h2>
        <div className="composer-quick-actions">
          <button
            type="button"
            className={rememberMode ? "active" : ""}
            disabled={sending}
            onClick={() => {
              setSkillMode(false);
              const next = !rememberMode;
              setRememberMode(next);
              if (next && !composer.startsWith("/remember ")) {
                setComposer((v) => (v.trim() ? `/remember ${v}` : "/remember "));
              }
            }}
          >
            记住{rememberMode ? " ✓" : ""}
          </button>
          <button
            type="button"
            className={skillMode ? "active" : ""}
            disabled={sending}
            onClick={() => {
              setRememberMode(false);
              const next = !skillMode;
              setSkillMode(next);
              if (next && !composer.startsWith("/skill ")) {
                setComposer((v) => (v.trim() ? `/skill ${v}` : "/skill "));
              }
            }}
          >
            技能{skillMode ? " ✓" : ""}
          </button>
        </div>
        <form onSubmit={onSubmit} className="composer-form">
          <textarea
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            onKeyDown={onComposerKeyDown}
            rows={3}
            placeholder="输入消息（Enter 发送，Shift+Enter 换行）"
            disabled={sending}
          />
          <div className="composer-actions">
            <button type="submit" disabled={sending || !composer.trim()}>
              {sending ? "运行中..." : selectedSessionId ? "发送到当前会话" : "新建会话并发送"}
            </button>
            {rememberMode ? <span className="mode-chip">remember mode</span> : null}
            {skillMode ? <span className="mode-chip">skill mode</span> : null}
            {sendError ? <span className="error-text">{sendError}</span> : null}
          </div>
        </form>
      </section>

      <section className="panel">
        <h2>Settings Snapshot</h2>
        {settings.isLoading ? (
          <p>Loading...</p>
        ) : settings.isError ? (
          <p>Failed: {(settings.error as Error).message}</p>
        ) : (
          <pre>{JSON.stringify(settings.data, null, 2)}</pre>
        )}
      </section>
    </main>
  );
}

function toolNameFromContent(content: string): string {
  const text = content.trim();
  if (!text.startsWith("[tool:")) return "tool";
  const end = text.indexOf("]");
  if (end <= 6) return "tool";
  return text.slice(6, end) || "tool";
}

function summarizeTraceEvent(
  eventType: string,
  payload: Record<string, unknown>
): string {
  if (eventType === "tool_executed") {
    const tool = String(payload.tool || "tool");
    const ok = Boolean(payload.ok);
    return `${tool} · ${ok ? "ok" : "error"}`;
  }
  if (eventType === "tool_denied") {
    return `denied · ${String(payload.reason || "unknown")}`;
  }
  if (eventType === "hook_blocked") {
    return `blocked by hook · ${String(payload.name || "")}`;
  }
  if (eventType === "budget_hard_exceeded") {
    return `budget hard · ${String(payload.dimension || "")}`;
  }
  if (eventType === "budget_soft_threshold") {
    return `budget soft · ${String(payload.dimension || "")}`;
  }
  if (eventType === "plan_emitted") {
    return "plan emitted";
  }
  if (eventType === "plan_recheck_requested") {
    return `recheck step=${String(payload.steps_used || "")}`;
  }
  return "event";
}

function MarkdownView({ markdown }: { markdown: string }) {
  const lines = markdown.split("\n");
  return (
    <div className="markdown-view">
      {lines.map((line, idx) => {
        if (line.startsWith("### ")) return <h4 key={idx}>{line.slice(4)}</h4>;
        if (line.startsWith("## ")) return <h3 key={idx}>{line.slice(3)}</h3>;
        if (line.startsWith("# ")) return <h2 key={idx}>{line.slice(2)}</h2>;
        if (line.startsWith("- ")) return <li key={idx}>{line.slice(2)}</li>;
        if (/^\d+\.\s+/.test(line)) return <li key={idx}>{line.replace(/^\d+\.\s+/, "")}</li>;
        if (!line.trim()) return <br key={idx} />;
        return <p key={idx}>{line}</p>;
      })}
    </div>
  );
}

function toTurnPayload(value: unknown): TurnPayload | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Partial<TurnPayload>;
  if (!raw.session || !raw.session.id) return null;
  if (!Array.isArray(raw.messages)) return null;
  return {
    session: raw.session as TurnPayload["session"],
    reply: String(raw.reply || ""),
    messages: raw.messages as TurnPayload["messages"],
    tool_cards: Array.isArray(raw.tool_cards) ? raw.tool_cards : [],
  };
}
