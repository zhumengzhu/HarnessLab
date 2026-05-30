const SESSION_KEY = "harnesslab.selectedSessionId";
const UI_MODE_KEY = "harnesslab.uiMode";
const ACTIVITY_DISPLAY_KEY = "harnesslab.activityDisplay";
const CHAT_TEXT_SIZE_KEY = "harnesslab.chatTextSize";
const UI_THEME_KEY = "harnesslab.uiTheme";

export type StoredUiMode = "simple" | "advanced";
export type StoredActivityDisplay = "compact" | "detailed";
export type StoredChatTextSize = "sm" | "md" | "lg";
export type StoredUiTheme = "dark" | "light";

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
    return raw === "dark" || raw === "light" ? raw : null;
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
