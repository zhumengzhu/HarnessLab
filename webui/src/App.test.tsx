import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      return jsonResponse({ ok: true, model: "simple", workspace: "/tmp" });
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

describe("App ui mode", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", createFetchMock());
  });

  afterEach(() => {
    cleanup();
  });

  it("defaults to simple mode and hides advanced panels", async () => {
    renderApp();

    expect(await screen.findByText("HarnessLab")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Proposals" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Settings" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Trace" })).toBeNull();
    expect(screen.getByTitle("新对话")).toBeTruthy();
  });

  it("shows advanced nav and separate views after switching mode", async () => {
    renderApp();
    await screen.findByText("HarnessLab");

    fireEvent.click(screen.getByRole("button", { name: "Advanced" }));

    await waitFor(() => {
      expect(screen.getByRole("navigation", { name: "Advanced" })).toBeTruthy();
    });

    expect(screen.queryByRole("heading", { name: "Proposals" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Proposals" }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Proposals" })).toBeTruthy();
    });
    expect(screen.queryByRole("heading", { name: "Trace" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Settings" })).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Chat" }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Trace" })).toBeTruthy();
    });
  });
});
