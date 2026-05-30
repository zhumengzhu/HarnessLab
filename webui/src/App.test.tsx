import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

function jsonResponse(payload: unknown, status: number = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function createFetchMock() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/health")) {
      return jsonResponse({ ok: true, model: "simple", workspace: "/tmp", version: "0.1.0" });
    }
    if (url.includes("/api/settings")) {
      return jsonResponse({ settings: { model_backend: "simple" } });
    }
    if (url.includes("/api/sessions?")) {
      return jsonResponse({ sessions: [] });
    }
    if (url.includes("/api/models")) {
      return jsonResponse({ models: [] });
    }
    if (url.includes("/api/proposals")) {
      return jsonResponse({ proposals: [] });
    }
    if (url.includes("/api/skills")) {
      return jsonResponse({ skills: [] });
    }
    return jsonResponse({ error: `unhandled ${url}` }, 404);
  });
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
}

describe("App shell", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", createFetchMock());
  });

  afterEach(() => {
    cleanup();
  });

  it("shows chat workspace with session tabs by default", async () => {
    renderApp();

    expect(await screen.findByRole("navigation", { name: /位置|Location/ })).toBeTruthy();
    expect(await screen.findByText("v0.1.0")).toBeTruthy();
    expect(screen.getByRole("tablist", { name: /会话视图|Session views/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /追踪|Trace/ })).toBeTruthy();
    expect(screen.getByTitle(/新对话|New chat/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /打开命令面板|Open command palette/ })).toBeTruthy();
  });

  it("navigates to settings and skills from sidebar", async () => {
    renderApp();
    await screen.findByRole("navigation", { name: /位置|Location/ });

    fireEvent.click(screen.getByRole("button", { name: /设置|Settings/ }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /设置|Settings/ })).toBeTruthy();
      expect(screen.getByText(/界面偏好|UI preferences/)).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: /技能|Skills/ }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: /技能|Skills/ })).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: /聊天|Chat/ }));
    await waitFor(() => {
      expect(screen.getByRole("tablist", { name: /会话视图|Session views/ })).toBeTruthy();
    });

    const sessionTabs = screen.getByRole("tablist", { name: /会话视图|Session views/ });
    fireEvent.click(within(sessionTabs).getByRole("tab", { name: /追踪|Trace/ }));
    await waitFor(() => {
      expect(document.querySelector(".trace-jaeger-panel")).toBeTruthy();
      expect(screen.getByRole("tab", { name: /Timeline/ })).toBeTruthy();
    });
  });

  it("collapses and expands the sidebar from the toggle control", async () => {
    renderApp();
    await screen.findByRole("navigation", { name: /位置|Location/ });

    const shell = document.querySelector(".app-shell");
    expect(shell?.classList.contains("app-shell-sidebar-collapsed")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /折叠侧栏|Collapse sidebar/ }));
    expect(shell?.classList.contains("app-shell-sidebar-collapsed")).toBe(true);
    expect(document.getElementById("app-sidebar")?.classList.contains("app-sidebar-collapsed")).toBe(
      true
    );

    fireEvent.click(screen.getByRole("button", { name: /展开侧栏|Expand sidebar/ }));
    expect(shell?.classList.contains("app-shell-sidebar-collapsed")).toBe(false);
  });
});
