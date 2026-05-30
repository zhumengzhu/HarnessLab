import type { ThemePreference } from "./theme";
import { useI18n } from "../../lib/i18n";
import { IconMonitor, IconMoon, IconSearch, IconSun } from "./icons";

type MainView = "chat" | "proposals" | "settings" | "skills" | "usage";

const MAIN_VIEW_KEYS: Record<MainView, "chat" | "proposals" | "settings" | "skills" | "usage"> = {
  chat: "chat",
  proposals: "proposals",
  settings: "settings",
  skills: "skills",
  usage: "usage",
};

type AppTopBarProps = {
  mainView: MainView;
  sessionTitle: string | null;
  focusMode: boolean;
  themePreference: ThemePreference;
  onThemePreferenceChange: (pref: ThemePreference) => void;
  onOpenCommandPalette: () => void;
  onExitFocusMode: () => void;
};

export function AppTopBar(props: AppTopBarProps) {
  const {
    mainView,
    sessionTitle,
    focusMode,
    themePreference,
    onThemePreferenceChange,
    onOpenCommandPalette,
    onExitFocusMode,
  } = props;
  const { t } = useI18n();

  return (
    <header className="app-topbar">
      <nav className="app-topbar-breadcrumb" aria-label={t("topbar.location")}>
        <span className="app-topbar-crumb">HarnessLab</span>
        <span className="app-topbar-sep">›</span>
        <span
          className={`app-topbar-crumb${mainView !== "chat" || !sessionTitle ? " app-topbar-crumb-active" : ""}`}
        >
          {t(`nav.${MAIN_VIEW_KEYS[mainView]}`)}
        </span>
        {mainView === "chat" && sessionTitle ? (
          <>
            <span className="app-topbar-sep">›</span>
            <span className="app-topbar-crumb app-topbar-crumb-active">{sessionTitle}</span>
          </>
        ) : null}
      </nav>

      <div className="app-topbar-actions">
        {focusMode ? (
          <button type="button" className="app-topbar-btn" onClick={onExitFocusMode}>
            {t("topbar.exitFocus")}
          </button>
        ) : null}
        <button
          type="button"
          className="app-topbar-search"
          onClick={onOpenCommandPalette}
          aria-label={t("topbar.openCommandPalette")}
        >
          <IconSearch size={15} />
          <span>{t("topbar.search")}</span>
          <kbd>⌘K</kbd>
        </button>
        <div className="app-topbar-theme" role="group" aria-label={t("topbar.theme")}>
          <button
            type="button"
            className={themePreference === "system" ? "active" : undefined}
            title={t("topbar.themeSystem")}
            aria-pressed={themePreference === "system"}
            onClick={() => onThemePreferenceChange("system")}
          >
            <IconMonitor size={15} />
          </button>
          <button
            type="button"
            className={themePreference === "light" ? "active" : undefined}
            title={t("topbar.themeLight")}
            aria-pressed={themePreference === "light"}
            onClick={() => onThemePreferenceChange("light")}
          >
            <IconSun size={15} />
          </button>
          <button
            type="button"
            className={themePreference === "dark" ? "active" : undefined}
            title={t("topbar.themeDark")}
            aria-pressed={themePreference === "dark"}
            onClick={() => onThemePreferenceChange("dark")}
          >
            <IconMoon size={15} />
          </button>
        </div>
      </div>
    </header>
  );
}
