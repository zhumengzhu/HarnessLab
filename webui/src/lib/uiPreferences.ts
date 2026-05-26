const SESSION_KEY = "harnesslab.selectedSessionId";
const UI_MODE_KEY = "harnesslab.uiMode";

export type StoredUiMode = "simple" | "advanced";

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
