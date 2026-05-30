import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, apiPost } from "./lib/api-client";
import { ActivityPanel } from "./features/activity/ActivityPanel";
import { ChildSessionsPanel } from "./features/sessions/ChildSessionsPanel";
import { buildActivityFeed } from "./features/activity/activityFeed";
import { ComposerPanel } from "./features/composer/ComposerPanel";
import { useComposerController } from "./features/composer/useComposerController";
import type { LiveTurnState } from "./features/live-turn/liveTurnReducer";
import { ProposalPanel } from "./features/proposals/ProposalPanel";
import { SessionWorkspace } from "./features/sessions/SessionWorkspace";
import { AppSidebar } from "./features/shell/AppSidebar";
import { SettingsPanel } from "./features/settings/SettingsPanel";
import { SkillBrowserPanel } from "./features/settings/SkillBrowserPanel";
import { TracePanel } from "./features/trace/TracePanel";
import { CheckpointPanel } from "./features/sessions/CheckpointPanel";
import {
  modelsForSessionPicker,
  resolveEffectiveModel,
} from "./lib/sessionModel";
import type { TurnEnrichment } from "./lib/turnEnrichments";
import {
  buildTurnEnrichmentsFromTrace,
  mergeTurnEnrichments,
} from "./lib/turnEnrichments";
import {
  loadStoredActivityDisplay,
  loadStoredChatTextSize,
  loadStoredSessionId,
  loadStoredUiMode,
  loadStoredUiTheme,
  saveStoredActivityDisplay,
  saveStoredChatTextSize,
  saveStoredSessionId,
  saveStoredUiMode,
  saveStoredUiTheme,
} from "./lib/uiPreferences";
import { applyUiTheme } from "./features/shell/theme";
import type { UiTheme } from "./features/shell/theme";
import { ChatDisplayProvider } from "./features/chat/chatDisplayPreferences";
import type { ActivityDisplayMode, ChatTextSize } from "./features/chat/chatDisplay";
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
  PatchSessionResponse,
  SessionDetailResponse,
  SessionsResponse,
  SettingsResponse,
  TraceResponse,
} from "./lib/schemas";

type MainView = "chat" | "proposals" | "settings" | "skills";

function isSessionNotFoundError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err);
  return message.includes("404") || /not found/i.test(message);
}

export function App() {
  const queryClient = useQueryClient();
  const [uiMode, setUiMode] = useState<"simple" | "advanced">(
    () => loadStoredUiMode() ?? "simple"
  );
  const [activityDisplay, setActivityDisplay] = useState<ActivityDisplayMode>(
    () => loadStoredActivityDisplay() ?? "detailed"
  );
  const [chatTextSize, setChatTextSize] = useState<ChatTextSize>(
    () => loadStoredChatTextSize() ?? "md"
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
  const [composerChromeCollapsed, setComposerChromeCollapsed] = useState(false);
  const [activityCleared, setActivityCleared] = useState(false);
  const [uiTheme, setUiTheme] = useState<UiTheme>(() => loadStoredUiTheme() ?? "dark");

  useEffect(() => {
    applyUiTheme(uiTheme);
    saveStoredUiTheme(uiTheme);
  }, [uiTheme]);

  function selectSession(id: string | null) {
    const switchingSession = id !== selectedSessionId;
    setSelectedSessionId(id);
    saveStoredSessionId(id);
    setSessionActionError(null);
    if (switchingSession) {
      setStreamTrace([]);
      setStreamMessages(null);
      setLiveContextSnapshot(null);
      setLiveTurn(null);
      setClientTurnEnrichments({});
      setComposerChromeCollapsed(false);
      setActivityCleared(false);
    }
    setMainView("chat");
  }

  /** Bind UI to a session created mid-turn without wiping streamed messages. */
  function adoptSessionId(id: string) {
    if (id === selectedSessionId) return;
    setSelectedSessionId(id);
    saveStoredSessionId(id);
    setSessionActionError(null);
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
    onAdoptSession: (id) => adoptSessionId(id),
    onAppendTraceEvent: (evt) => {
      setStreamTrace((prev) => [...prev, evt]);
      if (evt.event_type === "model_call") {
        const ctx = (evt.payload as Record<string, unknown>)["context"];
        if (ctx && typeof ctx === "object") {
          setLiveContextSnapshot(ctx as ContextSnapshot);
        }
      }
      if (evt.event_type === "sub_agent_spawned") {
        void queryClient.invalidateQueries({ queryKey: ["sessions"] });
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
    queryKey: ["sessions", selectedSessionId],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "50" });
      if (selectedSessionId) {
        params.set("include_id", selectedSessionId);
      }
      return apiGet<SessionsResponse>(`/api/sessions?${params.toString()}`);
    },
  });

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: () => apiGet<ModelsResponse>("/api/models"),
  });
  const sessionDetail = useQuery({
    queryKey: ["session", selectedSessionId],
    queryFn: () =>
      apiGet<SessionDetailResponse>(`/api/sessions/${encodeURIComponent(selectedSessionId || "")}`),
    enabled: Boolean(selectedSessionId),
    retry: (failureCount, error) => !isSessionNotFoundError(error) && failureCount < 2,
  });
  const sessionTrace = useQuery({
    queryKey: ["trace", selectedSessionId],
    queryFn: () =>
      apiGet<TraceResponse>(`/api/sessions/${encodeURIComponent(selectedSessionId || "")}/trace`),
    enabled: Boolean(selectedSessionId) && mainView === "chat",
  });

  useEffect(() => {
    if (!selectedSessionId || sessionDetail.isLoading || !sessionDetail.isError) return;
    if (isSessionNotFoundError(sessionDetail.error)) {
      setSelectedSessionId(null);
      saveStoredSessionId(null);
    }
  }, [
    selectedSessionId,
    sessionDetail.isLoading,
    sessionDetail.isError,
    sessionDetail.error,
  ]);

  const traceRows = useMemo(() => {
    const base = sessionTrace.data?.events || [];
    return [...base, ...streamTrace];
  }, [sessionTrace.data?.events, streamTrace]);

  const activityEntries = useMemo(() => {
    const source = activityCleared ? streamTrace : traceRows;
    return buildActivityFeed(source);
  }, [activityCleared, streamTrace, traceRows]);

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

  const childSessions = useMemo(() => {
    if (!selectedSessionId) return [];
    return (sessions.data?.sessions ?? []).filter(
      (s) => s.parent_session_id === selectedSessionId
    );
  }, [selectedSessionId, sessions.data?.sessions]);

  const parentSession = useMemo(() => {
    const parentId = sessionDetail.data?.session.parent_session_id;
    if (!parentId) return null;
    return (sessions.data?.sessions ?? []).find((s) => s.id === parentId) ?? null;
  }, [sessionDetail.data?.session.parent_session_id, sessions.data?.sessions]);

  const effectiveModel = useMemo(
    () =>
      resolveEffectiveModel(
        sessionDetail.data?.session,
        health.data,
        modelsQuery.data?.models ?? []
      ),
    [sessionDetail.data?.session, health.data, modelsQuery.data?.models]
  );
  const models: ModelInfo[] = useMemo(
    () =>
      modelsForSessionPicker(
        modelsQuery.data?.models ?? [],
        effectiveModel.modelId,
        effectiveModel.effort,
        effectiveModel.backend
      ),
    [modelsQuery.data?.models, effectiveModel]
  );
  const currentModelId = effectiveModel.modelId;
  const currentLabel = effectiveModel.label;

  async function handleModelSwitch(req: ModelSwitchRequest) {
    setModelSwitching(true);
    setModelSwitchError(null);
    try {
      if (selectedSessionId) {
        await apiPatch<PatchSessionResponse>(
          `/api/sessions/${encodeURIComponent(selectedSessionId)}`,
          {
            model_backend: req.backend ?? null,
            model_id: req.model_id ?? null,
            effort: req.effort ?? null,
          }
        );
        await queryClient.invalidateQueries({ queryKey: ["session", selectedSessionId] });
        await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      } else {
        await apiPost("/api/model", req as unknown as Record<string, unknown>);
        await queryClient.invalidateQueries({ queryKey: ["health"] });
        await queryClient.invalidateQueries({ queryKey: ["models"] });
      }
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

  function switchActivityDisplay(mode: ActivityDisplayMode) {
    setActivityDisplay(mode);
    saveStoredActivityDisplay(mode);
  }

  function switchChatTextSize(size: ChatTextSize) {
    setChatTextSize(size);
    saveStoredChatTextSize(size);
  }

  const chatDisplayValue = useMemo(
    () => ({
      activityDisplay,
      setActivityDisplay: switchActivityDisplay,
      chatTextSize,
      setChatTextSize: switchChatTextSize,
    }),
    [activityDisplay, chatTextSize]
  );

  return (
    <ChatDisplayProvider value={chatDisplayValue}>
    <div
      className={`app-shell${uiMode === "advanced" && mainView === "chat" ? " app-shell-with-trace" : ""}`}
    >
      <AppSidebar
        sessions={sessions.data?.sessions ?? []}
        selectedSessionId={selectedSessionId}
        sending={composerCtrl.sending}
        sessionsLoading={sessions.isLoading}
        sessionsError={sessions.isError ? (sessions.error as Error).message : null}
        sessionActionError={sessionActionError}
        uiMode={uiMode}
        mainView={mainView}
        healthOk={Boolean(health.data?.ok)}
        onSelectSession={selectSession}
        onForkCurrentSession={() => forkCurrentSession(composerCtrl.sending)}
        onUiModeChange={switchUiMode}
        onMainViewChange={setMainView}
        uiTheme={uiTheme}
        onUiThemeChange={setUiTheme}
      />

      <div className={`app-main chat-text-${chatTextSize}`}>
        {mainView === "chat" ? (
          <div className="app-chat-stack">
            <SessionWorkspace
              uiMode={uiMode}
              selectedSessionId={selectedSessionId}
              sending={composerCtrl.sending}
              sessionDetailLoading={sessionDetail.isLoading}
              sessionDetailError={
                sessionDetail.isError ? (sessionDetail.error as Error).message : null
              }
              sessionDetailData={sessionDetail.data}
              visibleMessages={chatRows}
              toolMessages={toolMessages}
              turnEnrichments={turnEnrichments}
              liveTurn={liveTurn}
              budgetEvents={budgetEvents}
              hasStreamMessages={(streamMessages?.length ?? 0) > 0}
              onComposerChromeChange={setComposerChromeCollapsed}
            />

            <ChildSessionsPanel
              parentSession={parentSession}
              childSessions={childSessions}
              selectedSessionId={selectedSessionId}
              onSelectSession={(id) => selectSession(id)}
            />

            <ActivityPanel
              entries={activityEntries}
              live={composerCtrl.sending}
              onClear={() => setActivityCleared(true)}
            />

            <div className="app-composer-dock">
              <ComposerPanel
                composer={composerCtrl.composer}
                sending={composerCtrl.sending}
                sendError={composerCtrl.sendError}
                queuedMessages={composerCtrl.queuedMessages}
                steeredMessages={composerCtrl.steeredMessages}
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
                selectedSessionId={selectedSessionId}
                onCompact={() => composerCtrl.sendCommand("/compact")}
                chromeCollapsed={composerChromeCollapsed}
              />
            </div>
          </div>
        ) : null}

        {mainView === "proposals" && uiMode === "advanced" ? (
          <div className="app-page-content">
            <ProposalPanel />
          </div>
        ) : null}

        {mainView === "settings" && uiMode === "advanced" ? (
          <div className="app-page-content">
            <SettingsPanel
              loading={settings.isLoading}
              error={settings.isError ? (settings.error as Error).message : null}
              data={settings.data}
            />
          </div>
        ) : null}

        {mainView === "skills" && uiMode === "advanced" ? (
          <div className="app-page-content">
            <SkillBrowserPanel />
          </div>
        ) : null}
      </div>

      {uiMode === "advanced" && mainView === "chat" ? (
        <aside className="app-trace-column">
          <CheckpointPanel
            sessionId={selectedSessionId}
            onRewindSuccess={() => {
              if (!selectedSessionId) return;
              void queryClient.invalidateQueries({ queryKey: ["session", selectedSessionId] });
              void queryClient.invalidateQueries({ queryKey: ["trace", selectedSessionId] });
            }}
          />
          <TracePanel
            selectedSessionId={selectedSessionId}
            loading={sessionTrace.isLoading}
            error={sessionTrace.isError ? (sessionTrace.error as Error).message : null}
            rows={traceRows}
            hasStreamTrace={streamTrace.length > 0}
            onClearStreamTrace={() => setStreamTrace([])}
          />
        </aside>
      ) : null}
    </div>
    </ChatDisplayProvider>
  );
}
