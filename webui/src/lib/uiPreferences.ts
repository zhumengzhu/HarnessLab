const SESSION_KEY = "harnesslab.selectedSessionId";
const UI_MODE_KEY = "harnesslab.uiMode";
const ACTIVITY_DISPLAY_KEY = "harnesslab.activityDisplay";
const CHAT_TEXT_SIZE_KEY = "harnesslab.chatTextSize";
const UI_THEME_KEY = "harnesslab.uiTheme";
const UI_THEME_FAMILY_KEY = "harnesslab.uiThemeFamily";

const SESSION_VIEW_TAB_KEY = "harnesslab.sessionViewTab";

export type StoredUiMode = "simple" | "advanced";
export type StoredActivityDisplay = "compact" | "detailed";
export type StoredChatTextSize = "sm" | "md" | "lg";
export type StoredUiTheme = "system" | "dark" | "light";
export type StoredThemeFamily = "claw" | "classic";
export type StoredLocale = "zh" | "en";
const SHOW_THINKING_KEY = "harnesslab.showThinking";
const SHOW_TOOLS_KEY = "harnesslab.showTools";
const FOCUS_MODE_KEY = "harnesslab.focusMode";
const LOCALE_KEY = "harnesslab.locale";
export type StoredSessionViewTab = "chat" | "trace" | "activity";

function canUseStorage(): boolean {
  try {
    return typeof localStorage !== "undefined";
  } catch {
    return false;
  }
}

export function loadStoredSessionId(): string | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw && raw.trim() ? raw.trim() : null;
  } catch {
    return null;
  }
}

export function saveStoredSessionId(sessionId: string | null): void {
  if (!canUseStorage()) return;
  try {
    if (sessionId) {
      localStorage.setItem(SESSION_KEY, sessionId);
    } else {
      localStorage.removeItem(SESSION_KEY);
    }
  } catch {
    /* ignore quota / privacy mode */
  }
}

export function loadStoredUiMode(): StoredUiMode | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(UI_MODE_KEY);
    return raw === "simple" || raw === "advanced" ? raw : null;
  } catch {
    return null;
  }
}

export function saveStoredUiMode(mode: StoredUiMode): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(UI_MODE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function loadStoredActivityDisplay(): StoredActivityDisplay | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(ACTIVITY_DISPLAY_KEY);
    return raw === "compact" || raw === "detailed" ? raw : null;
  } catch {
    return null;
  }
}

export function saveStoredActivityDisplay(mode: StoredActivityDisplay): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(ACTIVITY_DISPLAY_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function loadStoredChatTextSize(): StoredChatTextSize | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(CHAT_TEXT_SIZE_KEY);
    return raw === "sm" || raw === "md" || raw === "lg" ? raw : null;
  } catch {
    return null;
  }
}

export function saveStoredChatTextSize(size: StoredChatTextSize): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(CHAT_TEXT_SIZE_KEY, size);
  } catch {
    /* ignore */
  }
}

export function loadStoredUiTheme(): StoredUiTheme | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(UI_THEME_KEY);
    return raw === "system" || raw === "dark" || raw === "light" ? raw : null;
  } catch {
    return null;
  }
}

export function saveStoredUiTheme(theme: StoredUiTheme): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(UI_THEME_KEY, theme);
  } catch {
    /* ignore */
  }
}

export function loadStoredThemeFamily(): StoredThemeFamily | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(UI_THEME_FAMILY_KEY);
    return raw === "claw" || raw === "classic" ? raw : null;
  } catch {
    return null;
  }
}

export function saveStoredThemeFamily(family: StoredThemeFamily): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(UI_THEME_FAMILY_KEY, family);
  } catch {
    /* ignore */
  }
}

export function loadStoredSessionViewTab(): StoredSessionViewTab | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(SESSION_VIEW_TAB_KEY);
    return raw === "chat" || raw === "trace" || raw === "activity" ? raw : null;
  } catch {
    return null;
  }
}

export function saveStoredSessionViewTab(tab: StoredSessionViewTab): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(SESSION_VIEW_TAB_KEY, tab);
  } catch {
    /* ignore */
  }
}

export function loadStoredShowThinking(): boolean | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(SHOW_THINKING_KEY);
    if (raw === "true") return true;
    if (raw === "false") return false;
    return null;
  } catch {
    return null;
  }
}

export function saveStoredShowThinking(value: boolean): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(SHOW_THINKING_KEY, String(value));
  } catch {
    /* ignore */
  }
}

export function loadStoredShowTools(): boolean | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(SHOW_TOOLS_KEY);
    if (raw === "true") return true;
    if (raw === "false") return false;
    return null;
  } catch {
    return null;
  }
}

export function saveStoredShowTools(value: boolean): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(SHOW_TOOLS_KEY, String(value));
  } catch {
    /* ignore */
  }
}

export function loadStoredFocusMode(): boolean | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(FOCUS_MODE_KEY);
    if (raw === "true") return true;
    if (raw === "false") return false;
    return null;
  } catch {
    return null;
  }
}

export function saveStoredFocusMode(value: boolean): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(FOCUS_MODE_KEY, String(value));
  } catch {
    /* ignore */
  }
}

export function loadStoredLocale(): StoredLocale | null {
  if (!canUseStorage()) return null;
  try {
    const raw = localStorage.getItem(LOCALE_KEY);
    return raw === "zh" || raw === "en" ? raw : null;
  } catch {
    return null;
  }
}

export function saveStoredLocale(locale: StoredLocale): void {
  if (!canUseStorage()) return;
  try {
    localStorage.setItem(LOCALE_KEY, locale);
  } catch {
    /* ignore */
  }
}
