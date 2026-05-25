import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProposalPanel } from "./ProposalPanel";

function jsonResponse(payload: unknown, status: number = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ProposalPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("runs pytest gate and auto-checks pytest confirmation", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/proposals?status=open")) {
        return jsonResponse({
          proposals: [
            {
              id: "prop_1",
              status: "open",
              kind: "policy_denial",
              cluster_signature: "x",
              occurrences: 2,
              generated_at: "2026-05-25T00:00:00Z",
            },
          ],
        });
      }
      if (url.includes("/api/proposals/prop_1") && (!init || init.method !== "POST")) {
        return jsonResponse({
          proposal: {
            id: "prop_1",
            status: "open",
            kind: "policy_denial",
            cluster_signature: "x",
            occurrences: 2,
            generated_at: "2026-05-25T00:00:00Z",
            related_files: [],
            body_markdown: "## Suggested actions\n- tighten policy",
          },
        });
      }
      if (url.includes("/api/proposals/gates/run")) {
        return jsonResponse({
          result: {
            gate: "pytest",
            ok: true,
            exit_code: 0,
            elapsed_ms: 123,
            command: ["uv", "run", "pytest"],
            stdout: "all good",
            stderr: "",
            stdout_truncated: false,
            stderr_truncated: false,
          },
        });
      }
      return jsonResponse({ error: `unhandled ${url}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ProposalPanel />
      </QueryClientProvider>
    );

    const proposalButton = await screen.findByRole("button", { name: /prop_1/i });
    fireEvent.click(proposalButton);

    const runPytestButton = await screen.findByRole("button", {
      name: /Run uv run pytest/i,
    });
    fireEvent.click(runPytestButton);

    await waitFor(() => {
      const checkbox = screen.getByLabelText("`uv run pytest` 已通过") as HTMLInputElement;
      expect(checkbox.checked).toBe(true);
    });
  });

  it("does not auto-check pytest confirmation when gate fails", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/proposals?status=open")) {
        return jsonResponse({
          proposals: [
            {
              id: "prop_2",
              status: "open",
              kind: "tool_failure",
              cluster_signature: "y",
              occurrences: 3,
              generated_at: "2026-05-25T00:00:00Z",
            },
          ],
        });
      }
      if (url.includes("/api/proposals/prop_2") && (!init || init.method !== "POST")) {
        return jsonResponse({
          proposal: {
            id: "prop_2",
            status: "open",
            kind: "tool_failure",
            cluster_signature: "y",
            occurrences: 3,
            generated_at: "2026-05-25T00:00:00Z",
            related_files: [],
            body_markdown: "## Suggested actions\n- add guard",
          },
        });
      }
      if (url.includes("/api/proposals/gates/run")) {
        return jsonResponse({
          result: {
            gate: "pytest",
            ok: false,
            exit_code: 1,
            elapsed_ms: 321,
            command: ["uv", "run", "pytest"],
            stdout: "",
            stderr: "failed",
            stdout_truncated: false,
            stderr_truncated: false,
          },
        });
      }
      return jsonResponse({ error: `unhandled ${url}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ProposalPanel />
      </QueryClientProvider>
    );

    const proposalButton = await screen.findByRole("button", { name: /prop_2/i });
    fireEvent.click(proposalButton);

    const checkbox = await screen.findByLabelText("`uv run pytest` 已通过");
    expect((checkbox as HTMLInputElement).checked).toBe(false);
    fireEvent.change(checkbox, { target: { checked: true } });
    expect((checkbox as HTMLInputElement).checked).toBe(true);

    const runPytestButton = await screen.findByRole("button", {
      name: /Run uv run pytest/i,
    });
    fireEvent.click(runPytestButton);

    await waitFor(() => {
      expect((screen.getByLabelText("`uv run pytest` 已通过") as HTMLInputElement).checked).toBe(
        false
      );
    });
  });

  it("shows error text when gate API request fails", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/proposals?status=open")) {
        return jsonResponse({
          proposals: [
            {
              id: "prop_3",
              status: "open",
              kind: "runtime_error",
              cluster_signature: "z",
              occurrences: 1,
              generated_at: "2026-05-25T00:00:00Z",
            },
          ],
        });
      }
      if (url.includes("/api/proposals/prop_3") && (!init || init.method !== "POST")) {
        return jsonResponse({
          proposal: {
            id: "prop_3",
            status: "open",
            kind: "runtime_error",
            cluster_signature: "z",
            occurrences: 1,
            generated_at: "2026-05-25T00:00:00Z",
            related_files: [],
            body_markdown: "## Suggested actions\n- retry",
          },
        });
      }
      if (url.includes("/api/proposals/gates/run")) {
        return jsonResponse({ error: "gate backend unavailable" }, 500);
      }
      return jsonResponse({ error: `unhandled ${url}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ProposalPanel />
      </QueryClientProvider>
    );

    const proposalButton = await screen.findByRole("button", { name: /prop_3/i });
    fireEvent.click(proposalButton);

    const runPytestButton = await screen.findByRole("button", {
      name: /Run uv run pytest/i,
    });
    fireEvent.click(runPytestButton);

    await waitFor(() => {
      expect(screen.getByText("gate backend unavailable")).toBeTruthy();
    });
  });
});
