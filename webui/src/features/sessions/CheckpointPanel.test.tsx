import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CheckpointPanel } from "./CheckpointPanel";

function renderPanel(sessionId: string | null = "ses_test") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CheckpointPanel sessionId={sessionId} />
    </QueryClientProvider>
  );
}

describe("CheckpointPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows hint when no session is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/选择会话后可查看/)).toBeTruthy();
  });

  it("lists checkpoints and opens confirm dialog with diff preview", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/checkpoints/cp_1")) {
          return new Response(
            JSON.stringify({
              session_id: "ses_test",
              checkpoint: {
                id: "cp_1",
                tool_name: "write_file",
                tool_args: {},
                created_at: "2026-01-01T00:00:00Z",
              },
              changes: [
                {
                  path: "rewind.txt",
                  current: "v2\n",
                  restore_to: "v1\n",
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/checkpoints")) {
          return new Response(
            JSON.stringify({
              session_id: "ses_test",
              checkpoints: [
                {
                  id: "cp_1",
                  session_id: "ses_test",
                  tool_name: "write_file",
                  created_at: "2026-01-01T00:00:00Z",
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        return new Response(JSON.stringify({ error: "unhandled" }), { status: 404 });
      })
    );

    renderPanel("ses_test");

    expect(await screen.findByText("write_file")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Rewind…" }));

    await waitFor(() => {
      expect(screen.getByText("当前 workspace")).toBeTruthy();
      expect(screen.getByText("恢复后")).toBeTruthy();
      expect(screen.getByText("v2")).toBeTruthy();
      expect(screen.getByText("v1")).toBeTruthy();
    });
  });
});
