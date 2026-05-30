import { useMemo, useState } from "react";
import type { SessionSummary } from "../../lib/schemas";
import { useChatDisplay } from "../chat/chatDisplayPreferences";
import { stepChatTextSize } from "../chat/chatDisplay";
import { filterSessions, type SessionStatusFilter } from "./filterSessions";
import { SessionListItem } from "./SessionListItem";

type MainView = "chat" | "proposals" | "settings" | "skills";

type AppSidebarProps = {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  sending: boolean;
  sessionsLoading: boolean;
  sessionsError: string | null;
  sessionActionError: string | null;
  uiMode: "simple" | "advanced";
  mainView: MainView;
  healthOk: boolean;
  uiTheme: "dark" | "light";
  onUiThemeChange: (theme: "dark" | "light") => void;
  onSelectSession: (id: string | null) => void;
  onForkCurrentSession: () => void;
  onUiModeChange: (mode: "simple" | "advanced") => void;
  onMainViewChange: (view: MainView) => void;
};

const STATUS_FILTERS: Array<{ id: SessionStatusFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "running", label: "进行中" },
  { id: "done", label: "已完成" },
  { id: "waiting_user", label: "等待" },
  { id: "child", label: "子会话" },
];

export function AppSidebar(props: AppSidebarProps) {
  const {
    sessions,
    selectedSessionId,
    sending,
    sessionsLoading,
    sessionsError,
    sessionActionError,
    uiMode,
    mainView,
    healthOk,
    uiTheme,
    onUiThemeChange,
    onSelectSession,
    onForkCurrentSession,
    onUiModeChange,
    onMainViewChange,
  } = props;

  const { activityDisplay, setActivityDisplay, chatTextSize, setChatTextSize } =
    useChatDisplay();
  const [sessionQuery, setSessionQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<SessionStatusFilter>("all");

  const filteredSessions = useMemo(
    () =>
      filterSessions(sessions, {
        query: sessionQuery,
        status: statusFilter,
        pinSessionId: selectedSessionId,
      }),
    [sessions, sessionQuery, statusFilter, selectedSessionId]
  );

  const hasActiveFilter = sessionQuery.trim().length > 0 || statusFilter !== "all";

  return (
    <aside className="app-sidebar" aria-label="主导航">
      <div className="app-sidebar-brand">
        <strong className="app-sidebar-title">HarnessLab</strong>
        <span className="app-sidebar-health">{healthOk ? "health ok" : "health –"}</span>
      </div>

      <div className="app-sidebar-actions">
        <button
          type="button"
          className="app-sidebar-new"
          title="新对话"
          disabled={sending}
          onClick={() => onSelectSession(null)}
        >
          + 新对话
        </button>
        {selectedSessionId ? (
          <button
            type="button"
            className="app-sidebar-secondary"
            disabled={sending}
            onClick={onForkCurrentSession}
          >
            Fork
          </button>
        ) : null}
      </div>

      {sessionActionError ? (
        <p className="error-text app-sidebar-error">{sessionActionError}</p>
      ) : null}

      <div className="app-sidebar-section">
        <div className="app-sidebar-section-head">
          <h2 className="app-sidebar-heading">会话</h2>
          {!sessionsLoading && sessions.length > 0 ? (
            <span className="app-sidebar-count">
              {hasActiveFilter ? `${filteredSessions.length} / ${sessions.length}` : sessions.length}
            </span>
          ) : null}
        </div>

        <label className="app-sidebar-search">
          <span className="visually-hidden">搜索会话</span>
          <input
            type="search"
            value={sessionQuery}
            placeholder="搜索标题、目标或 ID…"
            aria-label="搜索会话"
            onChange={(event) => setSessionQuery(event.target.value)}
          />
        </label>

        <div className="app-session-filters" role="group" aria-label="会话筛选">
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.id}
              type="button"
              className={statusFilter === filter.id ? "active" : ""}
              aria-pressed={statusFilter === filter.id}
              onClick={() => setStatusFilter(filter.id)}
            >
              {filter.label}
            </button>
          ))}
        </div>

        {sessionsLoading ? <p className="app-sidebar-hint">Loading…</p> : null}
        {sessionsError ? <p className="error-text app-sidebar-error">{sessionsError}</p> : null}

        <ul className="app-session-list" role="listbox" aria-label="历史会话">
          {filteredSessions.map((session) => (
            <SessionListItem
              key={session.id}
              session={session}
              selected={selectedSessionId === session.id}
              onSelect={() => onSelectSession(session.id)}
            />
          ))}
          {!sessionsLoading && sessions.length === 0 ? (
            <li className="app-sidebar-hint">暂无历史会话</li>
          ) : null}
          {!sessionsLoading && sessions.length > 0 && filteredSessions.length === 0 ? (
            <li className="app-sidebar-hint">无匹配会话</li>
          ) : null}
        </ul>
      </div>

      <div className="app-sidebar-footer">
        <div className="app-sidebar-display" role="group" aria-label="活动展示">
          <span className="app-sidebar-display-label">活动</span>
          <button
            type="button"
            className={activityDisplay === "compact" ? "active" : ""}
            aria-pressed={activityDisplay === "compact"}
            onClick={() => setActivityDisplay("compact")}
          >
            简洁
          </button>
          <button
            type="button"
            className={activityDisplay === "detailed" ? "active" : ""}
            aria-pressed={activityDisplay === "detailed"}
            onClick={() => setActivityDisplay("detailed")}
          >
            详细
          </button>
        </div>

        <div className="app-sidebar-text-size" role="group" aria-label="字号">
          <button
            type="button"
            aria-label="减小字号"
            disabled={chatTextSize === "sm"}
            onClick={() => setChatTextSize(stepChatTextSize(chatTextSize, -1))}
          >
            A−
          </button>
          <span className="app-sidebar-text-size-label">{chatTextSize.toUpperCase()}</span>
          <button
            type="button"
            aria-label="增大字号"
            disabled={chatTextSize === "lg"}
            onClick={() => setChatTextSize(stepChatTextSize(chatTextSize, 1))}
          >
            A+
          </button>
        </div>

        <div className="app-sidebar-theme" role="group" aria-label="主题">
          <span className="app-sidebar-display-label">主题</span>
          <button
            type="button"
            className={uiTheme === "dark" ? "active" : ""}
            aria-pressed={uiTheme === "dark"}
            onClick={() => onUiThemeChange("dark")}
          >
            暗
          </button>
          <button
            type="button"
            className={uiTheme === "light" ? "active" : ""}
            aria-pressed={uiTheme === "light"}
            onClick={() => onUiThemeChange("light")}
          >
            亮
          </button>
        </div>

        <div className="mode-switch app-sidebar-mode" role="group" aria-label="UI 模式">
          <button
            type="button"
            className={uiMode === "simple" ? "active" : ""}
            onClick={() => onUiModeChange("simple")}
          >
            Simple
          </button>
          <button
            type="button"
            className={uiMode === "advanced" ? "active" : ""}
            onClick={() => onUiModeChange("advanced")}
          >
            Advanced
          </button>
        </div>

        {uiMode === "advanced" ? (
          <nav className="app-sidebar-nav" aria-label="Advanced">
            <button
              type="button"
              className={mainView === "chat" ? "active" : ""}
              onClick={() => onMainViewChange("chat")}
            >
              Chat
            </button>
            <button
              type="button"
              className={mainView === "proposals" ? "active" : ""}
              onClick={() => onMainViewChange("proposals")}
            >
              Proposals
            </button>
            <button
              type="button"
              className={mainView === "skills" ? "active" : ""}
              onClick={() => onMainViewChange("skills")}
            >
              Skills
            </button>
            <button
              type="button"
              className={mainView === "settings" ? "active" : ""}
              onClick={() => onMainViewChange("settings")}
            >
              Settings
            </button>
          </nav>
        ) : null}
      </div>
    </aside>
  );
}
