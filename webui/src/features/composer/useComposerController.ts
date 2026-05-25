import type { FormEvent, KeyboardEvent } from "react";
import { useState } from "react";
import type { QueryClient } from "@tanstack/react-query";
import { postSse } from "../../lib/sse-client";
import type {
  ContextSnapshot,
  MessageItem,
  ToolCard,
  TurnPayload,
  TraceEventItem,
} from "../../lib/schemas";

type UseComposerControllerArgs = {
  selectedSessionId: string | null;
  queryClient: QueryClient;
  onBeforeSend: () => void;
  onSelectSession: (id: string) => void;
  onAppendTraceEvent: (evt: TraceEventItem) => void;
  onSetStreamMessages: (messages: MessageItem[] | null) => void;
  onSetStreamToolCards: (cards: ToolCard[]) => void;
  onContextSnapshot?: (ctx: ContextSnapshot | null) => void;
};

type UseComposerControllerResult = {
  composer: string;
  setComposer: (value: string) => void;
  sending: boolean;
  sendError: string | null;
  rememberMode: boolean;
  skillMode: boolean;
  onSubmit: (e: FormEvent<HTMLFormElement>) => Promise<void>;
  onComposerKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  toggleRememberMode: () => void;
  toggleSkillMode: () => void;
};

export function useComposerController(
  args: UseComposerControllerArgs
): UseComposerControllerResult {
  const {
    selectedSessionId,
    queryClient,
    onBeforeSend,
    onSelectSession,
    onAppendTraceEvent,
    onSetStreamMessages,
    onSetStreamToolCards,
    onContextSnapshot,
  } = args;

  const [composer, setComposerState] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [rememberMode, setRememberMode] = useState(false);
  const [skillMode, setSkillMode] = useState(false);

  function setComposer(value: string) {
    setComposerState(value);
  }

  function prepareOutgoingText(text: string): string {
    const trimmed = text.trim();
    if (!trimmed) return "";
    if (rememberMode || trimmed.startsWith("/remember ")) {
      setRememberMode(false);
      if (trimmed.startsWith("/remember ")) return trimmed;
      return `/remember ${trimmed}`;
    }
    if (skillMode || trimmed.startsWith("/skill")) {
      setSkillMode(false);
      if (trimmed.startsWith("/skill")) return trimmed;
      return `/skill ${trimmed}`;
    }
    return trimmed;
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const outgoing = prepareOutgoingText(composer);
    if (!outgoing || sending) return;
    setSending(true);
    setSendError(null);
    onBeforeSend();
    onSetStreamToolCards([]);
    try {
      const path = selectedSessionId
        ? `/api/sessions/${encodeURIComponent(selectedSessionId)}/messages`
        : "/api/sessions";
      let donePayload: unknown = null;
      await postSse(
        path,
        { message: outgoing },
        {
          onTrace: (payload) => {
            onAppendTraceEvent(payload as TraceEventItem);
          },
          onDone: (payload) => {
            donePayload = payload as TurnPayload;
          },
          onError: (message) => {
            setSendError(message);
          },
        }
      );
      const finalPayload = toTurnPayload(donePayload);
      if (finalPayload) {
        onSelectSession(finalPayload.session.id);
        onSetStreamMessages(finalPayload.messages);
        onSetStreamToolCards(finalPayload.tool_cards || []);
        if (onContextSnapshot && finalPayload.context_snapshot !== undefined) {
          onContextSnapshot(finalPayload.context_snapshot ?? null);
        }
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["sessions"] }),
          queryClient.invalidateQueries({ queryKey: ["session", finalPayload.session.id] }),
          queryClient.invalidateQueries({ queryKey: ["trace", finalPayload.session.id] }),
        ]);
      }
      setComposerState("");
    } catch (err) {
      setSendError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  function onComposerKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sending && composer.trim()) {
        e.currentTarget.form?.requestSubmit();
      }
    }
  }

  function toggleRememberMode() {
    setSkillMode(false);
    const next = !rememberMode;
    setRememberMode(next);
    if (next && !composer.startsWith("/remember ")) {
      setComposerState((v) => (v.trim() ? `/remember ${v}` : "/remember "));
    }
  }

  function toggleSkillMode() {
    setRememberMode(false);
    const next = !skillMode;
    setSkillMode(next);
    if (next && !composer.startsWith("/skill ")) {
      setComposerState((v) => (v.trim() ? `/skill ${v}` : "/skill "));
    }
  }

  return {
    composer,
    setComposer,
    sending,
    sendError,
    rememberMode,
    skillMode,
    onSubmit,
    onComposerKeyDown,
    toggleRememberMode,
    toggleSkillMode,
  };
}

function toTurnPayload(value: unknown): TurnPayload | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Partial<TurnPayload>;
  if (!raw.session || !raw.session.id) return null;
  if (!Array.isArray(raw.messages)) return null;
  return {
    session: raw.session as TurnPayload["session"],
    reply: String(raw.reply || ""),
    messages: raw.messages as TurnPayload["messages"],
    tool_cards: Array.isArray(raw.tool_cards) ? raw.tool_cards : [],
  };
}
