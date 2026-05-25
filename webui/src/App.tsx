import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./lib/api-client";
import { ComposerPanel } from "./features/composer/ComposerPanel";
import { useComposerController } from "./features/composer/useComposerController";
import { ProposalPanel } from "./features/proposals/ProposalPanel";
import { SessionWorkspace } from "./features/sessions/SessionWorkspace";
import { SettingsPanel } from "./features/settings/SettingsPanel";
import type {
  ForkResponse,
  HealthResponse,
  MessageItem,
  SessionDetailResponse,
  SessionsResponse,
  SettingsResponse,
  ToolCard,
  TraceResponse,
} from "./lib/schemas";

export function App() {
  const queryClient = useQueryClient();
  const [uiMode, setUiMode] = useState<"simple" | "advanced">("simple");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionActionError, setSessionActionError] = useState<string | null>(null);
  const [streamTrace, setStreamTrace] = useState<TraceResponse["events"]>([]);
  const [streamToolCards, setStreamToolCards] = useState<ToolCard[]>([]);
  const [streamMessages, setStreamMessages] = useState<MessageItem[] | null>(null);

  function selectSession(id: string | null) {
    setSelectedSessionId(id);
    setSessionActionError(null);
    setStreamTrace([]);
    setStreamToolCards([]);
    setStreamMessages(null);
  }

  async function forkCurrentSession(sending: boolean) {
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

  const composerCtrl = useComposerController({
    selectedSessionId,
    queryClient,
    onBeforeSend: () => {
      setSessionActionError(null);
      setStreamTrace([]);
    },
    onSelectSession: (id) => selectSession(id),
    onAppendTraceEvent: (evt) => setStreamTrace((prev) => [...prev, evt]),
    onSetStreamMessages: setStreamMessages,
    onSetStreamToolCards: setStreamToolCards,
  });

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
    enabled: Boolean(selectedSessionId) && uiMode === "advanced",
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
  const budgetEvents = useMemo(() => {
    return traceRows.filter((e) =>
      [
        "budget_soft_threshold",
        "budget_hard_exceeded",
        "budget_enforcement_action",
      ].includes(e.event_type)
    );
  }, [traceRows]);

  return (
    <main className="page">
      <header className="header">
        <div>
          <h1>HarnessLab TS UI (Phase D start)</h1>
          <p>
            {uiMode === "simple"
              ? "Simple Chat Mode: 聚焦会话与聊天。"
              : "Advanced Mode: 会话诊断、proposal 审阅与设置快照。"}
          </p>
        </div>
        <div className="header-meta">
          <div className="mode-switch">
            <button
              type="button"
              className={uiMode === "simple" ? "active" : ""}
              onClick={() => setUiMode("simple")}
            >
              Simple
            </button>
            <button
              type="button"
              className={uiMode === "advanced" ? "active" : ""}
              onClick={() => setUiMode("advanced")}
            >
              Advanced
            </button>
          </div>
          <span>{health.data?.ok ? "health: ok" : "health: -"}</span>
          <span>model: {health.data?.model || "-"}</span>
        </div>
      </header>

      <SessionWorkspace
        selectedSessionId={selectedSessionId}
        sending={composerCtrl.sending}
        sessionActionError={sessionActionError}
        sessionsLoading={sessions.isLoading}
        sessionsError={sessions.isError ? (sessions.error as Error).message : null}
        sessionsRows={sessions.data?.sessions || []}
        sessionDetailLoading={sessionDetail.isLoading}
        sessionDetailError={sessionDetail.isError ? (sessionDetail.error as Error).message : null}
        sessionDetailData={sessionDetail.data}
        sessionTraceLoading={sessionTrace.isLoading}
        sessionTraceError={sessionTrace.isError ? (sessionTrace.error as Error).message : null}
        traceRows={traceRows}
        visibleMessages={visibleMessages}
        toolMessages={toolMessages}
        streamToolCards={streamToolCards}
        budgetEvents={budgetEvents}
        hasStreamTrace={streamTrace.length > 0}
        uiMode={uiMode}
        onSelectSession={selectSession}
        onForkCurrentSession={() => forkCurrentSession(composerCtrl.sending)}
        onClearStreamTrace={() => setStreamTrace([])}
      />

      {uiMode === "advanced" ? <ProposalPanel /> : null}

      <ComposerPanel
        composer={composerCtrl.composer}
        sending={composerCtrl.sending}
        sendError={composerCtrl.sendError}
        rememberMode={composerCtrl.rememberMode}
        skillMode={composerCtrl.skillMode}
        selectedSessionId={selectedSessionId}
        onSubmit={composerCtrl.onSubmit}
        onComposerChange={composerCtrl.setComposer}
        onToggleRememberMode={composerCtrl.toggleRememberMode}
        onToggleSkillMode={composerCtrl.toggleSkillMode}
        onComposerKeyDown={composerCtrl.onComposerKeyDown}
      />

      {uiMode === "advanced" ? (
        <SettingsPanel
          loading={settings.isLoading}
          error={settings.isError ? (settings.error as Error).message : null}
          data={settings.data}
        />
      ) : null}
    </main>
  );
}
