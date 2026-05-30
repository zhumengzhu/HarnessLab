import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { SessionSummary } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { filterSessions, type SessionStatusFilter } from "./filterSessions";
import { SessionListItem } from "./SessionListItem";
import { SidebarTooltip } from "./SidebarTooltip";
import {
  IconChevron,
  IconFileText,
  IconHistory,
  IconMessage,
  IconPanelLeftClose,
  IconPanelLeftOpen,
  IconPlus,
  IconSettings,
  IconSparkles,
} from "./icons";
import { SHOW_PROPOSALS_UI } from "./featureFlags";
import { SidebarVersion } from "./SidebarVersion";

type MainView = "chat" | "proposals" | "settings" | "skills" | "usage";

type AppSidebarProps = {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  sending: boolean;
  sessionsLoading: boolean;
  sessionsError: string | null;
  sessionActionError: string | null;
  mainView: MainView;
  healthOk: boolean;
  version: string | null | undefined;
  focusMode: boolean;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onSelectSession: (id: string | null) => void;
  onForkCurrentSession: () => void;
  onMainViewChange: (view: MainView) => void;
};

const STATUS_FILTER_IDS: SessionStatusFilter[] = [
  "all",
  "running",
  "done",
  "waiting_user",
  "child",
];

const FILTER_LABEL_KEYS: Record<
  SessionStatusFilter,
  "nav.filterAll" | "nav.filterRunning" | "nav.filterDone" | "nav.filterWaiting" | "nav.filterChild"
> = {
  all: "nav.filterAll",
  running: "nav.filterRunning",
  done: "nav.filterDone",
  waiting_user: "nav.filterWaiting",
  child: "nav.filterChild",
};

type NavItem = {
  id: MainView;
  labelKey: "nav.chat" | "nav.proposals" | "nav.skills" | "nav.usage" | "nav.settings";
  icon: ReactNode;
  group: "chat" | "workspace" | "system";
};

const ALL_NAV_ITEMS: NavItem[] = [
  { id: "chat", labelKey: "nav.chat", icon: <IconMessage size={16} />, group: "chat" },
  { id: "proposals", labelKey: "nav.proposals", icon: <IconFileText size={16} />, group: "workspace" },
  { id: "skills", labelKey: "nav.skills", icon: <IconSparkles size={16} />, group: "workspace" },
  { id: "usage", labelKey: "nav.usage", icon: <IconHistory size={16} />, group: "workspace" },
  { id: "settings", labelKey: "nav.settings", icon: <IconSettings size={16} />, group: "system" },
];

const NAV_ITEMS = ALL_NAV_ITEMS.filter((item) => SHOW_PROPOSALS_UI || item.id !== "proposals");

const GROUP_LABEL_KEYS: Record<
  NavItem["group"],
  "nav.groupChat" | "nav.groupWorkspace" | "nav.groupSystem"
> = {
  chat: "nav.groupChat",
  workspace: "nav.groupWorkspace",
  system: "nav.groupSystem",
};

function SidebarNavButton(props: {
  label: string;
  active?: boolean;
  collapsed: boolean;
  disabled?: boolean;
  icon: ReactNode;
  onClick: () => void;
  className?: string;
}) {
  const { label, active, collapsed, disabled, icon, onClick, className = "app-sidebar-nav-item" } =
    props;
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="app-sidebar-nav-wrap"
      onMouseEnter={collapsed ? () => setHovered(true) : undefined}
      onMouseLeave={collapsed ? () => setHovered(false) : undefined}
    >
      <button
        ref={buttonRef}
        type="button"
        className={`${className}${active ? " active" : ""}`}
        disabled={disabled}
        aria-label={collapsed ? label : undefined}
        aria-current={active ? "page" : undefined}
        onClick={onClick}
        onFocus={collapsed ? () => setHovered(true) : undefined}
        onBlur={collapsed ? () => setHovered(false) : undefined}
      >
        {icon}
        <span>{label}</span>
      </button>
      {collapsed && hovered && buttonRef.current ? (
        <SidebarTooltip anchor={buttonRef.current} label={label} />
      ) : null}
    </div>
  );
}

export function AppSidebar(props: AppSidebarProps) {
  const {
    sessions,
    selectedSessionId,
    sending,
    sessionsLoading,
    sessionsError,
    sessionActionError,
    mainView,
    healthOk,
    version,
    focusMode,
    collapsed,
    onToggleCollapsed,
    onSelectSession,
    onForkCurrentSession,
    onMainViewChange,
  } = props;

  const { t } = useI18n();
  const [sessionQuery, setSessionQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<SessionStatusFilter>("all");
  const [chatOpen, setChatOpen] = useState(true);

  const filteredSessions = useMemo(
    () =>
      filterSessions(sessions, {
        query: sessionQuery,
        status: statusFilter,
        pinSessionId: selectedSessionId,
      }),
    [sessions, sessionQuery, statusFilter, selectedSessionId]
  );

  if (focusMode) {
    return null;
  }

  const groups: NavItem["group"][] = ["chat", "workspace", "system"];

  return (
    <aside
      id="app-sidebar"
      className={`app-sidebar app-sidebar-card${collapsed ? " app-sidebar-collapsed" : ""}`}
      aria-label={t("nav.mainNav")}
      aria-expanded={!collapsed}
    >
      <div className="app-sidebar-brand">
        <div className="app-sidebar-logo" aria-hidden>
          HL
        </div>
        {!collapsed ? (
          <div className="app-sidebar-brand-text">
            <strong className="app-sidebar-title">HarnessLab</strong>
            <span className="app-sidebar-health">
              {healthOk ? t("nav.healthOk") : t("nav.healthBad")}
            </span>
          </div>
        ) : null}
        <button
          type="button"
          className="app-sidebar-collapse-btn"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")}
          title={collapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")}
        >
          {collapsed ? <IconPanelLeftOpen size={16} /> : <IconPanelLeftClose size={16} />}
        </button>
      </div>

      {groups.map((group) => (
        <section key={group} className="app-sidebar-group">
          {!collapsed ? (
            <h2 className="app-sidebar-group-label">{t(GROUP_LABEL_KEYS[group])}</h2>
          ) : null}
          <nav className="app-sidebar-nav" aria-label={t(GROUP_LABEL_KEYS[group])}>
            {NAV_ITEMS.filter((item) => item.group === group).map((item) => (
              <SidebarNavButton
                key={item.id}
                label={t(item.labelKey)}
                icon={item.icon}
                active={mainView === item.id}
                collapsed={collapsed}
                onClick={() => onMainViewChange(item.id)}
              />
            ))}
          </nav>
        </section>
      ))}

      {collapsed && mainView === "chat" ? (
        <div className="app-sidebar-collapsed-actions">
          <SidebarNavButton
            label={t("nav.newChat")}
            icon={<IconPlus size={16} />}
            collapsed={collapsed}
            disabled={sending}
            className="app-sidebar-nav-item app-sidebar-icon-action"
            onClick={() => onSelectSession(null)}
          />
        </div>
      ) : null}

      {!collapsed && mainView === "chat" ? (
        <section className="app-sidebar-group app-sidebar-sessions-group">
          <button
            type="button"
            className="app-sidebar-group-toggle"
            aria-expanded={chatOpen}
            onClick={() => setChatOpen((open) => !open)}
          >
            <span>{t("nav.sessions")}</span>
            <IconChevron open={chatOpen} size={14} />
          </button>

          {chatOpen ? (
            <>
              <div className="app-sidebar-actions">
                <button
                  type="button"
                  className="app-sidebar-new"
                  title={t("nav.newChat")}
                  disabled={sending}
                  onClick={() => onSelectSession(null)}
                >
                  + {t("nav.newChat")}
                </button>
                {selectedSessionId ? (
                  <button
                    type="button"
                    className="app-sidebar-secondary"
                    disabled={sending}
                    onClick={onForkCurrentSession}
                  >
                    {t("nav.fork")}
                  </button>
                ) : null}
              </div>

              {sessionActionError ? (
                <p className="error-text app-sidebar-error">{sessionActionError}</p>
              ) : null}

              <label className="app-sidebar-search">
                <span className="visually-hidden">{t("nav.searchSessions")}</span>
                <input
                  type="search"
                  value={sessionQuery}
                  placeholder={t("nav.searchSessions")}
                  aria-label={t("nav.searchSessions")}
                  onChange={(event) => setSessionQuery(event.target.value)}
                />
              </label>

              <div className="app-session-filters" role="group" aria-label={t("nav.sessions")}>
                {STATUS_FILTER_IDS.map((filterId) => (
                  <button
                    key={filterId}
                    type="button"
                    className={statusFilter === filterId ? "active" : ""}
                    aria-pressed={statusFilter === filterId}
                    onClick={() => setStatusFilter(filterId)}
                  >
                    {t(FILTER_LABEL_KEYS[filterId])}
                  </button>
                ))}
              </div>

              {sessionsLoading ? <p className="app-sidebar-hint">{t("common.loading")}</p> : null}
              {sessionsError ? <p className="error-text app-sidebar-error">{sessionsError}</p> : null}

              <ul className="app-session-list" role="listbox" aria-label={t("nav.sessionList")}>
                {filteredSessions.map((session) => (
                  <SessionListItem
                    key={session.id}
                    session={session}
                    selected={selectedSessionId === session.id}
                    onSelect={() => onSelectSession(session.id)}
                  />
                ))}
                {!sessionsLoading && sessions.length === 0 ? (
                  <li className="app-sidebar-hint">{t("nav.noSessions")}</li>
                ) : null}
                {!sessionsLoading && sessions.length > 0 && filteredSessions.length === 0 ? (
                  <li className="app-sidebar-hint">{t("nav.noMatch")}</li>
                ) : null}
              </ul>
            </>
          ) : null}
        </section>
      ) : null}

      <footer className="app-sidebar-footer">
        <SidebarVersion version={version} healthOk={healthOk} collapsed={collapsed} />
      </footer>
    </aside>
  );
}
