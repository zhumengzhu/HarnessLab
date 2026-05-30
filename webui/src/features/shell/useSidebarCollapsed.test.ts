import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  SIDEBAR_COLLAPSED_STORAGE_KEY,
  readSidebarCollapsedPreference,
  useSidebarCollapsed,
} from "./useSidebarCollapsed";

function createStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
  };
}

describe("useSidebarCollapsed", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", createStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("defaults to expanded when storage is empty", () => {
    expect(readSidebarCollapsedPreference()).toBe(false);
    const { result } = renderHook(() => useSidebarCollapsed());
    expect(result.current.collapsed).toBe(false);
  });

  it("reads persisted preference", () => {
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, "true");
    expect(readSidebarCollapsedPreference()).toBe(true);
  });

  it("toggleCollapsed persists to localStorage", () => {
    const { result } = renderHook(() => useSidebarCollapsed());

    act(() => {
      result.current.toggleCollapsed();
    });

    expect(result.current.collapsed).toBe(true);
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe("true");

    act(() => {
      result.current.toggleCollapsed();
    });

    expect(result.current.collapsed).toBe(false);
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe("false");
  });
});
