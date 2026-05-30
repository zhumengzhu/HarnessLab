import { useCallback, useState } from "react";

export const SIDEBAR_COLLAPSED_STORAGE_KEY = "harnesslab-sidebar-collapsed";

export function readSidebarCollapsedPreference(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(readSidebarCollapsedPreference);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(next));
      } catch {
        /* localStorage may be unavailable */
      }
      return next;
    });
  }, []);

  return { collapsed, toggleCollapsed, setCollapsed };
}
