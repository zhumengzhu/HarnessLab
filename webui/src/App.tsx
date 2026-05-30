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
import { SHOW_PROPOSALS_UI } from "./features/shell/featureFlags";
import { SessionWorkspace } from "./features/sessions/SessionWorkspace";
import { SessionViewTabs } from "./features/sessions/SessionViewTabs";
import type { SessionViewTab } from "./features/sessions/SessionViewTabs";
import { SessionTraceView } from "./features/sessions/SessionTraceView";
import { AppSidebar } from "./features/shell/AppSidebar";
import { AppTopBar } from "./features/shell/AppTopBar";
import { useSidebarCollapsed } from "./features/shell/useSidebarCollapsed";
import {
  CommandPalette,
  useCommandPaletteShortcut,
  type CommandPaletteAction,
} from "./features/shell/CommandPalette";
import { ChatSessionHeader } from "./features/chat/ChatSessionHeader";
import { DEFAULT_AGENT_PERSONA } from "./lib/agentPersona";
import { SettingsPanel } from "./features/settings/SettingsPanel";
import { SkillBrowserPanel } from "./features/settings/SkillBrowserPanel";
import { UsagePanel } from "./features/usage/UsagePanel";
import {
  modelsForSessionPicker,
  resolveEffectiveModel,
} from "./lib/sessionModel";
import type { TurnEnrichment } from "./lib/turnEnrichments";
import { isChatMessageVisible } from "./lib/messageVisibility";
import {
  buildTurnEnrichmentsFromTrace,
  mergeTurnEnrichments,
} from "./lib/turnEnrichments";
import {
  loadStoredActivityDisplay,
  loadStoredChatTextSize,
  loadStoredFocusMode,
  loadStoredLocale,
  loadStoredSessionId,
  loadStoredSessionViewTab,
  loadStoredShowThinking,
  loadStoredShowTools,
  loadStoredThemeFamily,
  loadStoredUiTheme,
  saveStoredActivityDisplay,
  saveStoredChatTextSize,
  saveStoredFocusMode,
  saveStoredLocale,
  saveStoredSessionId,
  saveStoredSessionViewTab,
  saveStoredShowThinking,
  saveStoredShowTools,
  saveStoredThemeFamily,
  saveStoredUiTheme,
} from "./lib/uiPreferences";
import {
  applyUiTheme,
  resolveUiTheme,
  type ThemeFamily,
  type ThemePreference,
} from "./features/shell/theme";
import { I18nProvider, translate, type Locale } from "./lib/i18n";
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

type MainView = "chat" | "proposals" | "settings" | "skills" | "usage";

function isSessionNotFoundError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err);
  return message.includes("404") || /not found/i.test(message);
}

export function App() {
  const queryClient = useQueryClient();
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
  const [themeFamily, setThemeFamily] = useState<ThemeFamily>(
    () => loadStoredThemeFamily() ?? "claw"
  );
  const [themePreference, setThemePreference] = useState<ThemePreference>(
    () => loadStoredUiTheme() ?? "system"
  );
  const [showThinking, setShowThinking] = useState(
    () => loadStoredShowThinking() ?? true
  );
  const [showTools, setShowTools] = useState(() => loadStoredShowTools() ?? true);
  const [focusMode, setFocusMode] = useState(() => loadStoredFocusMode() ?? false);
  const { collapsed: sidebarCollapsed, toggleCollapsed: toggleSidebarCollapsed } =
    useSidebarCollapsed();
  const [locale, setLocale] = useState<Locale>(() => {
    const stored = loadStoredLocale();
    if (stored) return stored;
    if (typeof navigator !== "undefined" && navigator.language.toLowerCase().startsWith("zh")) {
      return "zh";
    }
    return "en";
  });
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [sessionViewTab, setSessionViewTab] = useState<SessionViewTab>(
    () => loadStoredSessionViewTab() ?? "chat"
  );

  useEffect(() => {
    applyUiTheme(resolveUiTheme(themeFamily, themePreference));
    saveStoredUiTheme(themePreference);
    saveStoredThemeFamily(themeFamily);
  }, [themeFamily, themePreference]);

  useEffect(() => {
    if (themePreference !== "system") return;
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyUiTheme(resolveUiTheme(themeFamily, "system"));
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [themeFamily, themePreference]);

  useCommandPaletteShortcut(() => setCommandPaletteOpen(true));

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
    enabled: mainView === "settings",
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
    return rows.filter((m) =>
      isChatMessageVisible(m, { showThinking, showTools }, turnEnrichments[m.id])
    );
  }, [
    sessionDetail.data?.messages,
    streamMessages,
    showThinking,
    showTools,
    turnEnrichments,
  ]);

  const chatRows = useMemo(() => {
    if (!liveTurn) return visibleMessages;
    const pendingUserId = liveTurn.userMessage.id;
    const withoutDuplicateUser = visibleMessages.filter((m) => m.id !== pendingUserId);
    return [...withoutDuplicateUser, liveTurn.userMessage];
  }, [liveTurn, visibleMessages]);

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

  function switchSessionViewTab(tab: SessionViewTab) {
    setSessionViewTab(tab);
    saveStoredSessionViewTab(tab);
  }

  function switchActivityDisplay(mode: ActivityDisplayMode) {
    setActivityDisplay(mode);
    saveStoredActivityDisplay(mode);
  }

  function switchChatTextSize(size: ChatTextSize) {
    setChatTextSize(size);
    saveStoredChatTextSize(size);
  }

  function switchShowThinking(value: boolean) {
    setShowThinking(value);
    saveStoredShowThinking(value);
  }

  function switchShowTools(value: boolean) {
    setShowTools(value);
    saveStoredShowTools(value);
  }

  function switchFocusMode(value: boolean) {
    setFocusMode(value);
    saveStoredFocusMode(value);
  }

  function switchLocale(next: Locale) {
    setLocale(next);
    saveStoredLocale(next);
  }

  const currentSessionSummary = useMemo(
    () => (sessions.data?.sessions ?? []).find((s) => s.id === selectedSessionId) ?? null,
    [sessions.data?.sessions, selectedSessionId]
  );

  const commandActions = useMemo((): CommandPaletteAction[] => {
    const t = (key: string) => translate(locale, key);
    const nav: CommandPaletteAction[] = [
      {
        id: "nav-chat",
        label: t("command.openChat"),
        group: t("command.nav"),
        run: () => setMainView("chat"),
      },
      {
        id: "nav-settings",
        label: t("command.openSettings"),
        group: t("command.nav"),
        run: () => setMainView("settings"),
      },
      ...(SHOW_PROPOSALS_UI
        ? ([
            {
              id: "nav-proposals",
              label: t("command.openProposals"),
              group: t("command.nav"),
              run: () => setMainView("proposals"),
            },
          ] satisfies CommandPaletteAction[])
        : []),
      {
        id: "nav-skills",
        label: t("command.openSkills"),
        group: t("command.nav"),
        run: () => setMainView("skills"),
      },
      {
        id: "nav-usage",
        label: t("command.openUsage"),
        group: t("command.nav"),
        run: () => setMainView("usage"),
      },
      {
        id: "nav-trace",
        label: t("command.openTrace"),
        group: t("command.nav"),
        run: () => {
          setMainView("chat");
          setSessionViewTab("trace");
        },
      },
      {
        id: "cmd-compact",
        label: t("command.compact"),
        group: t("command.cmd"),
        run: () => composerCtrl.sendCommand("/compact"),
      },
      {
        id: "cmd-skill-list",
        label: t("command.skillList"),
        group: t("command.cmd"),
        hint: "/skill list",
        run: () => composerCtrl.setComposer("/skill list"),
      },
    ];
    const sessionActions = (sessions.data?.sessions ?? []).slice(0, 20).map((session) => ({
      id: `session-${session.id}`,
      label: session.title || session.goal || session.id,
      group: t("command.sessions"),
      hint: session.id,
      run: () => selectSession(session.id),
    }));
    return [...nav, ...sessionActions];
  }, [sessions.data?.sessions, composerCtrl, locale]);

  const chatDisplayValue = useMemo(
    () => ({
      activityDisplay,
      setActivityDisplay: switchActivityDisplay,
      chatTextSize,
      setChatTextSize: switchChatTextSize,
      showThinking,
      setShowThinking: switchShowThinking,
      showTools,
      setShowTools: switchShowTools,
    }),
    [activityDisplay, chatTextSize, showThinking, showTools]
  );

  return (
    <I18nProvider locale={locale} onLocaleChange={switchLocale}>
    <ChatDisplayProvider value={chatDisplayValue}>
    <div
      className={`app-shell${focusMode ? " app-shell-focus" : ""}${
        sidebarCollapsed ? " app-shell-sidebar-collapsed" : ""
      }`}
    >
      <AppSidebar
        sessions={sessions.data?.sessions ?? []}
        selectedSessionId={selectedSessionId}
        sending={composerCtrl.sending}
        sessionsLoading={sessions.isLoading}
        sessionsError={sessions.isError ? (sessions.error as Error).message : null}
        sessionActionError={sessionActionError}
        mainView={mainView}
        healthOk={Boolean(health.data?.ok)}
        version={health.data?.version}
        focusMode={focusMode}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={toggleSidebarCollapsed}
        onSelectSession={selectSession}
        onForkCurrentSession={() => forkCurrentSession(composerCtrl.sending)}
        onMainViewChange={setMainView}
      />

      <div className={`app-main chat-text-${chatTextSize}`}>
        <AppTopBar
          mainView={mainView}
          sessionTitle={
            currentSessionSummary?.title ||
            currentSessionSummary?.goal ||
            (selectedSessionId ? selectedSessionId.slice(0, 12) : null)
          }
          focusMode={focusMode}
          themePreference={themePreference}
          onThemePreferenceChange={setThemePreference}
          onOpenCommandPalette={() => setCommandPaletteOpen(true)}
          onExitFocusMode={() => switchFocusMode(false)}
        />

        <CommandPalette
          open={commandPaletteOpen}
          onClose={() => setCommandPaletteOpen(false)}
          actions={commandActions}
        />
        {mainView === "chat" ? (
          <div className="app-session-view">
            <SessionViewTabs
              value={sessionViewTab}
              onChange={switchSessionViewTab}
              showTrace
            />
            <div className="app-session-view-body">
              {sessionViewTab === "chat" ? (
                <>
                  <ChatSessionHeader
                    session={currentSessionSummary}
                    sessionId={selectedSessionId}
                    currentModelId={currentModelId}
                    currentLabel={currentLabel}
                    models={models}
                    modelSwitching={modelSwitching}
                    modelSwitchError={modelSwitchError}
                    showThinking={showThinking}
                    showTools={showTools}
                    focusMode={focusMode}
                    onModelSwitch={handleModelSwitch}
                    onDismissModelError={() => setModelSwitchError(null)}
                    onToggleThinking={() => switchShowThinking(!showThinking)}
                    onToggleTools={() => switchShowTools(!showTools)}
                    onToggleFocus={() => switchFocusMode(!focusMode)}
                    onRefresh={() => {
                      if (!selectedSessionId) return;
                      void queryClient.invalidateQueries({ queryKey: ["session", selectedSessionId] });
                      void queryClient.invalidateQueries({ queryKey: ["trace", selectedSessionId] });
                    }}
                  />

                  <SessionWorkspace
                    selectedSessionId={selectedSessionId}
                    sessionDetailLoading={sessionDetail.isLoading}
                    sessionDetailError={
                      sessionDetail.isError ? (sessionDetail.error as Error).message : null
                    }
                    sessionDetailData={sessionDetail.data}
                    visibleMessages={chatRows}
                    turnEnrichments={turnEnrichments}
                    liveTurn={liveTurn}
                    hasStreamMessages={(streamMessages?.length ?? 0) > 0}
                    persona={DEFAULT_AGENT_PERSONA}
                    contextSnapshot={displayedContext}
                    modelLabel={currentLabel}
                    onPickPrompt={(text) => composerCtrl.setComposer(text)}
                    onComposerChromeChange={setComposerChromeCollapsed}
                  />

                  <ChildSessionsPanel
                    parentSession={parentSession}
                    childSessions={childSessions}
                    selectedSessionId={selectedSessionId}
                    onSelectSession={(id) => selectSession(id)}
                  />

                  <div className="app-composer-dock">
                    <ComposerPanel
                      composer={composerCtrl.composer}
                      sending={composerCtrl.sending}
                      sendError={composerCtrl.sendError}
                      queuedCount={composerCtrl.queuedMessages.length}
                      steeredCount={composerCtrl.steeredMessages.length}
                      rememberMode={composerCtrl.rememberMode}
                      slashMenu={composerCtrl.slashMenu}
                      agentMode={agentMode}
                      onAgentModeChange={setAgentMode}
                      contextSnapshot={displayedContext}
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
                      agentName={DEFAULT_AGENT_PERSONA.name}
                      chromeCollapsed={composerChromeCollapsed}
                    />
                  </div>
                </>
              ) : null}

              {sessionViewTab === "trace" ? (
                <SessionTraceView
                  sessionId={selectedSessionId}
                  loading={sessionTrace.isLoading}
                  error={sessionTrace.isError ? (sessionTrace.error as Error).message : null}
                  rows={traceRows}
                  hasStreamTrace={streamTrace.length > 0}
                  onClearStreamTrace={() => setStreamTrace([])}
                  onRewindSuccess={() => {
                    if (!selectedSessionId) return;
                    void queryClient.invalidateQueries({ queryKey: ["session", selectedSessionId] });
                    void queryClient.invalidateQueries({ queryKey: ["trace", selectedSessionId] });
                  }}
                />
              ) : null}

              {sessionViewTab === "activity" ? (
                <ActivityPanel
                  entries={activityEntries}
                  live={composerCtrl.sending}
                  onClear={() => setActivityCleared(true)}
                  fullPage
                />
              ) : null}
            </div>
          </div>
        ) : null}

        {SHOW_PROPOSALS_UI && mainView === "proposals" ? (
          <div className="app-page-content">
            <ProposalPanel />
          </div>
        ) : null}

        {mainView === "settings" ? (
          <div className="app-page-content">
            <SettingsPanel
              loading={settings.isLoading}
              error={settings.isError ? (settings.error as Error).message : null}
              data={settings.data}
              health={health.data}
              healthLoading={health.isLoading}
              themeFamily={themeFamily}
              onThemeFamilyChange={setThemeFamily}
              themePreference={themePreference}
              onThemePreferenceChange={setThemePreference}
              locale={locale}
              onLocaleChange={switchLocale}
              activityDisplay={activityDisplay}
              onActivityDisplayChange={switchActivityDisplay}
              chatTextSize={chatTextSize}
              onChatTextSizeChange={switchChatTextSize}
            />
          </div>
        ) : null}

        {mainView === "skills" ? (
          <div className="app-page-content">
            <SkillBrowserPanel />
          </div>
        ) : null}

        {mainView === "usage" ? (
          <div className="app-page-content">
            <UsagePanel />
          </div>
        ) : null}
      </div>
    </div>
    </ChatDisplayProvider>
    </I18nProvider>
  );
}
