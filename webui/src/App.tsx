import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./lib/api-client";
import { ChatTopBar } from "./features/chat/ChatTopBar";
import { ComposerPanel } from "./features/composer/ComposerPanel";
import { useComposerController } from "./features/composer/useComposerController";
import type { LiveTurnState } from "./features/live-turn/liveTurnReducer";
import { ProposalPanel } from "./features/proposals/ProposalPanel";
import { SessionWorkspace } from "./features/sessions/SessionWorkspace";
import { SettingsPanel } from "./features/settings/SettingsPanel";
import type { TurnEnrichment } from "./lib/turnEnrichments";
import {
  buildTurnEnrichmentsFromTrace,
  mergeTurnEnrichments,
} from "./lib/turnEnrichments";
import {
  loadStoredSessionId,
  loadStoredUiMode,
  saveStoredSessionId,
  saveStoredUiMode,
} from "./lib/uiPreferences";
import type { AgentMode } from "./features/chat/AgentModeSelector";
import type {
  ContextResponse,
  ContextSnapshot,
  ForkResponse,
  HealthResponse,
  MessageItem,
  ModelInfo,
  ModelSwitchRequest,
  ModelsResponse,
  SessionDetailResponse,
  SessionsResponse,
  SettingsResponse,
  TraceResponse,
} from "./lib/schemas";

type MainView = "chat" | "proposals" | "settings";

export function App() {
  const queryClient = useQueryClient();
  const [uiMode, setUiMode] = useState<"simple" | "advanced">(
    () => loadStoredUiMode() ?? "simple"
  );
  const [mainView, setMainView] = useState<MainView>("chat");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    () => loadStoredSessionId()
  );
  const [sessionActionError, setSessionActionError] = useState<string | null>(null);
  const [streamTrace, setStreamTrace] = useState<TraceResponse["events"]>([]);
  const [streamMessages, setStreamMessages] = useState<MessageItem[] | null>(null);
  const [liveContextSnapshot, setLiveContextSnapshot] = useState<ContextSnapshot | null>(null);
  const [liveTurn, setLiveTurn] = useState<LiveTurnState | null>(null);
  const [clientTurnEnrichments, setClientTurnEnrichments] = useState<
    Record<string, TurnEnrichment>
  >({});

  const [agentMode, setAgentMode] = useState<AgentMode>("agent");
  const [modelSwitching, setModelSwitching] = useState(false);
  const [modelSwitchError, setModelSwitchError] = useState<string | null>(null);

  function selectSession(id: string | null) {
    setSelectedSessionId(id);
    saveStoredSessionId(id);
    setSessionActionError(null);
    setStreamTrace([]);
    setStreamMessages(null);
    setLiveContextSnapshot(null);
    setLiveTurn(null);
    setClientTurnEnrichments({});
    setMainView("chat");
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
    onAppendTraceEvent: (evt) => {
      setStreamTrace((prev) => [...prev, evt]);
      if (evt.event_type === "model_call") {
        const ctx = (evt.payload as Record<string, unknown>)["context"];
        if (ctx && typeof ctx === "object") {
          setLiveContextSnapshot(ctx as ContextSnapshot);
        }
      }
    },
    onSetStreamMessages: setStreamMessages,
    onSetStreamToolCards: () => {},
    onContextSnapshot: (ctx) => setLiveContextSnapshot(ctx),
    onLiveTurnStart: setLiveTurn,
    onLiveTurnEvent: setLiveTurn,
    onLiveTurnEnd: () => setLiveTurn(null),
    onLiveTurnStop: () => {},
    onTurnEnriched: (messageId, enrichment) => {
      setClientTurnEnrichments((prev) => ({ ...prev, [messageId]: enrichment }));
    },
  });

  const sessionContext = useQuery({
    queryKey: ["context", selectedSessionId],
    queryFn: () =>
      apiGet<ContextResponse>(
        `/api/sessions/${encodeURIComponent(selectedSessionId || "")}/context`
      ),
    enabled: Boolean(selectedSessionId),
  });
  const displayedContext =
    liveContextSnapshot ?? sessionContext.data?.context ?? null;

  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => apiGet<HealthResponse>("/api/health"),
  });
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGet<SettingsResponse>("/api/settings"),
    enabled: uiMode === "advanced" && mainView === "settings",
  });
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () => apiGet<SessionsResponse>("/api/sessions?limit=50"),
  });

  useEffect(() => {
    if (!sessions.data || selectedSessionId === null) return;
    const exists = sessions.data.sessions.some((s) => s.id === selectedSessionId);
    if (!exists) {
      setSelectedSessionId(null);
      saveStoredSessionId(null);
    }
  }, [sessions.data, selectedSessionId]);

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: () => apiGet<ModelsResponse>("/api/models"),
  });
  const sessionDetail = useQuery({
    queryKey: ["session", selectedSessionId],
    queryFn: () =>
      apiGet<SessionDetailResponse>(`/api/sessions/${encodeURIComponent(selectedSessionId || "")}`),
    enabled: Boolean(selectedSessionId) && mainView === "chat",
  });
  const sessionTrace = useQuery({
    queryKey: ["trace", selectedSessionId],
    queryFn: () =>
      apiGet<TraceResponse>(`/api/sessions/${encodeURIComponent(selectedSessionId || "")}/trace`),
    enabled: Boolean(selectedSessionId) && mainView === "chat",
  });

  const traceRows = useMemo(() => {
    const base = sessionTrace.data?.events || [];
    return [...base, ...streamTrace];
  }, [sessionTrace.data?.events, streamTrace]);

  const allMessages = streamMessages ?? sessionDetail.data?.messages ?? [];
  const traceDerivedEnrichments = useMemo(
    () => buildTurnEnrichmentsFromTrace(allMessages, traceRows),
    [allMessages, traceRows]
  );
  const turnEnrichments = useMemo(
    () => mergeTurnEnrichments(traceDerivedEnrichments, clientTurnEnrichments),
    [traceDerivedEnrichments, clientTurnEnrichments]
  );

  const visibleMessages = useMemo(() => {
    const rows = streamMessages ?? sessionDetail.data?.messages ?? [];
    return rows.filter(
      (m) =>
        m.role === "user" ||
        (m.role === "assistant" && (m.content.trim() || m.reasoning_text))
    );
  }, [sessionDetail.data?.messages, streamMessages]);

  const chatRows = useMemo(() => {
    if (!liveTurn) return visibleMessages;
    const pendingUserId = liveTurn.userMessage.id;
    const withoutDuplicateUser = visibleMessages.filter((m) => m.id !== pendingUserId);
    return [...withoutDuplicateUser, liveTurn.userMessage];
  }, [liveTurn, visibleMessages]);

  const toolMessages = useMemo(() => {
    const rows = streamMessages ?? sessionDetail.data?.messages ?? [];
    return rows.filter((m) => m.role === "tool");
  }, [sessionDetail.data?.messages, streamMessages]);
  const budgetEvents = useMemo(() => {
    return traceRows.filter((e) =>
      [
        "budget_soft_threshold",
        "budget_hard_exceeded",
        "budget_enforcement_action",
      ].includes(e.event_type)
    );
  }, [traceRows]);

  const currentModelId = health.data?.model_id ?? null;
  const currentLabel = health.data?.model_label ?? health.data?.model ?? "–";
  const models: ModelInfo[] = modelsQuery.data?.models ?? [];

  async function handleModelSwitch(req: ModelSwitchRequest) {
    setModelSwitching(true);
    setModelSwitchError(null);
    try {
      await apiPost("/api/model", req as unknown as Record<string, unknown>);
      await queryClient.invalidateQueries({ queryKey: ["health"] });
      await queryClient.invalidateQueries({ queryKey: ["models"] });
    } catch (err) {
      setModelSwitchError((err as Error).message);
    } finally {
      setModelSwitching(false);
    }
  }

  function switchUiMode(mode: "simple" | "advanced") {
    setUiMode(mode);
    saveStoredUiMode(mode);
    if (mode === "simple") {
      setMainView("chat");
    }
  }

  return (
    <main className="page">
      <header className="header">
        <div>
          <h1>HarnessLab</h1>
          <p>
            {uiMode === "simple"
              ? "Simple Chat — 聚焦对话。"
              : "Advanced — 诊断、Proposals 与 Settings 独立页面。"}
          </p>
        </div>
        <div className="header-meta">
          {uiMode === "advanced" ? (
            <nav className="main-nav" aria-label="Main">
              <button
                type="button"
                className={mainView === "chat" ? "active" : ""}
                onClick={() => setMainView("chat")}
              >
                Chat
              </button>
              <button
                type="button"
                className={mainView === "proposals" ? "active" : ""}
                onClick={() => setMainView("proposals")}
              >
                Proposals
              </button>
              <button
                type="button"
                className={mainView === "settings" ? "active" : ""}
                onClick={() => setMainView("settings")}
              >
                Settings
              </button>
            </nav>
          ) : null}
          <div className="mode-switch">
            <button
              type="button"
              className={uiMode === "simple" ? "active" : ""}
              onClick={() => switchUiMode("simple")}
            >
              Simple
            </button>
            <button
              type="button"
              className={uiMode === "advanced" ? "active" : ""}
              onClick={() => switchUiMode("advanced")}
            >
              Advanced
            </button>
          </div>
          <span>{health.data?.ok ? "health: ok" : "health: –"}</span>
        </div>
      </header>

      {mainView === "chat" ? (
        <>
          <ChatTopBar
            sessions={sessions.data?.sessions ?? []}
            selectedSessionId={selectedSessionId}
            sending={composerCtrl.sending}
            sessionsLoading={sessions.isLoading}
            sessionsError={sessions.isError ? (sessions.error as Error).message : null}
            sessionActionError={sessionActionError}
            onSelectSession={selectSession}
            onForkCurrentSession={() => forkCurrentSession(composerCtrl.sending)}
          />

          <SessionWorkspace
            uiMode={uiMode}
            selectedSessionId={selectedSessionId}
            sending={composerCtrl.sending}
            sessionDetailLoading={sessionDetail.isLoading}
            sessionDetailError={sessionDetail.isError ? (sessionDetail.error as Error).message : null}
            sessionDetailData={sessionDetail.data}
            sessionTraceLoading={sessionTrace.isLoading}
            sessionTraceError={sessionTrace.isError ? (sessionTrace.error as Error).message : null}
            traceRows={traceRows}
            visibleMessages={chatRows}
            toolMessages={toolMessages}
            turnEnrichments={turnEnrichments}
            liveTurn={liveTurn}
            budgetEvents={budgetEvents}
            hasStreamTrace={streamTrace.length > 0}
            onClearStreamTrace={() => setStreamTrace([])}
          />

          <ComposerPanel
            composer={composerCtrl.composer}
            sending={composerCtrl.sending}
            sendError={composerCtrl.sendError}
            queuedMessages={composerCtrl.queuedMessages}
            rememberMode={composerCtrl.rememberMode}
            slashMenu={composerCtrl.slashMenu}
            agentMode={agentMode}
            onAgentModeChange={setAgentMode}
            currentModelId={currentModelId}
            currentLabel={currentLabel}
            models={models}
            modelSwitching={modelSwitching}
            modelSwitchError={modelSwitchError}
            contextSnapshot={displayedContext}
            onModelSwitch={handleModelSwitch}
            onDismissModelError={() => setModelSwitchError(null)}
            onSubmit={composerCtrl.onSubmit}
            onSend={composerCtrl.onSend}
            onStop={composerCtrl.onStop}
            onComposerChange={composerCtrl.setComposer}
            onToggleRememberMode={composerCtrl.toggleRememberMode}
            onPickSlashItem={composerCtrl.pickSlashItem}
            onComposerKeyDown={composerCtrl.onComposerKeyDown}
            onCompositionStart={composerCtrl.onCompositionStart}
            onCompositionEnd={composerCtrl.onCompositionEnd}
          />
        </>
      ) : null}

      {mainView === "proposals" && uiMode === "advanced" ? <ProposalPanel /> : null}

      {mainView === "settings" && uiMode === "advanced" ? (
        <SettingsPanel
          loading={settings.isLoading}
          error={settings.isError ? (settings.error as Error).message : null}
          data={settings.data}
        />
      ) : null}
    </main>
  );
}
