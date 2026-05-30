import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useComposerController } from "./useComposerController";
import type { TurnPayload } from "../../lib/schemas";

const postSseMock = vi.fn();

vi.mock("../../lib/sse-client", () => ({
  postSse: (...args: unknown[]) => postSseMock(...args),
}));

vi.mock("../../lib/api-client", () => ({
  apiGet: vi.fn(async () => ({ commands: [], skills: [] })),
  apiPost: vi.fn(),
}));

function turnPayload(sessionId: string): TurnPayload {
  return {
    session: {
      id: sessionId,
      goal: "test",
      status: "running",
      turn_count: 1,
      step_count: 1,
      created_at: "2026-01-01T00:00:00Z",
      last_step_at: "2026-01-01T00:00:01Z",
      parent_session_id: null,
      title: "test",
      message_count: 2,
      budget_usage: undefined,
    },
    reply: "done",
    messages: [
      {
        id: "msg_u1",
        role: "user",
        content: "hello",
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "msg_a1",
        role: "assistant",
        content: "done",
        created_at: "2026-01-01T00:00:01Z",
      },
    ],
    tool_cards: [],
  };
}

function renderComposerController(
  args: Parameters<typeof useComposerController>[0]
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useComposerController(args), { wrapper });
}

describe("useComposerController session selection", () => {
  it("does not re-select the same session after a turn completes", async () => {
    postSseMock.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        handlers: { onDone: (payload: TurnPayload) => void }
      ) => {
        handlers.onDone(turnPayload("ses_same"));
      }
    );

    const onAdoptSession = vi.fn();
    const onSetStreamMessages = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderComposerController({
      selectedSessionId: "ses_same",
      queryClient,
      onBeforeSend: vi.fn(),
      onAdoptSession,
      onAppendSpan: vi.fn(),
      onSetStreamMessages,
      onSetStreamToolCards: vi.fn(),
    });

    act(() => {
      result.current.setComposer("hello");
    });
    await waitFor(() => expect(result.current.composer).toBe("hello"));
    await act(async () => {
      result.current.onSend();
    });
    await waitFor(() => expect(result.current.sending).toBe(false));

    expect(onAdoptSession).not.toHaveBeenCalled();
    expect(onSetStreamMessages).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ id: "msg_a1" })])
    );
  });

  it("adopts a new session when the first turn creates one", async () => {
    postSseMock.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        handlers: { onDone: (payload: TurnPayload) => void }
      ) => {
        handlers.onDone(turnPayload("ses_new"));
      }
    );

    const onAdoptSession = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderComposerController({
      selectedSessionId: null,
      queryClient,
      onBeforeSend: vi.fn(),
      onAdoptSession,
      onAppendSpan: vi.fn(),
      onSetStreamMessages: vi.fn(),
      onSetStreamToolCards: vi.fn(),
    });

    act(() => {
      result.current.setComposer("hello");
    });
    await waitFor(() => expect(result.current.composer).toBe("hello"));
    await act(async () => {
      result.current.onSend();
    });
    await waitFor(() => expect(result.current.sending).toBe(false));

    expect(onAdoptSession).toHaveBeenCalledWith("ses_new");
  });

  it("does not adopt when a turn started on an existing session", async () => {
    postSseMock.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        handlers: { onDone: (payload: TurnPayload) => void }
      ) => {
        handlers.onDone(turnPayload("ses_other"));
      }
    );

    const onAdoptSession = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderComposerController({
      selectedSessionId: "ses_existing",
      queryClient,
      onBeforeSend: vi.fn(),
      onAdoptSession,
      onAppendSpan: vi.fn(),
      onSetStreamMessages: vi.fn(),
      onSetStreamToolCards: vi.fn(),
    });

    act(() => {
      result.current.setComposer("hello");
    });
    await waitFor(() => expect(result.current.composer).toBe("hello"));
    await act(async () => {
      result.current.onSend();
    });
    await waitFor(() => expect(result.current.sending).toBe(false));

    expect(onAdoptSession).not.toHaveBeenCalled();
  });
});
