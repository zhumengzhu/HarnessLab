import type { CompositionEvent, FormEvent, KeyboardEvent } from "react";
import { useRef, useState } from "react";
import type { QueryClient } from "@tanstack/react-query";
import { apiPost } from "../../lib/api-client";
import { shouldSubmitComposerOnEnter } from "../../lib/composerEnter";
import { postSse } from "../../lib/sse-client";
import type {
  ContextSnapshot,
  MessageItem,
  ToolCard,
  TurnPayload,
  TraceEventItem,
} from "../../lib/schemas";
import type { TurnEnrichment } from "../../lib/turnEnrichments";
import {
  enrichmentFromLiveTurn,
  findTerminalAssistantMessage,
} from "../../lib/turnEnrichments";
import type { LiveTurnState } from "../live-turn/liveTurnReducer";
import {
  createLiveTurn,
  finalizeLiveTurn,
  reduceLiveTurn,
  stopLiveTurn,
} from "../live-turn/liveTurnReducer";
import { applyLiveTurnDelta } from "../live-turn/liveTurnStream";
import { isSlashPaletteOpen, useComposerSlashMenu } from "./useComposerSlashMenu";

type UseComposerControllerArgs = {
  selectedSessionId: string | null;
  queryClient: QueryClient;
  onBeforeSend: () => void;
  onAdoptSession: (id: string) => void;
  onAppendTraceEvent: (evt: TraceEventItem) => void;
  onSetStreamMessages: (messages: MessageItem[] | null) => void;
  onSetStreamToolCards: (cards: ToolCard[]) => void;
  onContextSnapshot?: (ctx: ContextSnapshot | null) => void;
  onLiveTurnStart?: (turn: LiveTurnState) => void;
  onLiveTurnEvent?: (turn: LiveTurnState) => void;
  onLiveTurnEnd?: () => void;
  onLiveTurnStop?: () => void;
  onTurnEnriched?: (messageId: string, enrichment: TurnEnrichment) => void;
};

type UseComposerControllerResult = {
  composer: string;
  setComposer: (value: string) => void;
  sending: boolean;
  sendError: string | null;
  rememberMode: boolean;
  slashMenu: ReturnType<typeof useComposerSlashMenu>;
  queuedMessages: string[];
  steeredMessages: string[];
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onSend: () => void;
  onStop: () => void;
  onComposerKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  onCompositionStart: (e: CompositionEvent<HTMLTextAreaElement>) => void;
  onCompositionEnd: (e: CompositionEvent<HTMLTextAreaElement>) => void;
  toggleRememberMode: () => void;
  pickSlashItem: (insert: string) => void;
  sendCommand: (command: string) => void;
};

export function useComposerController(
  args: UseComposerControllerArgs
): UseComposerControllerResult {
  const {
    selectedSessionId,
    queryClient,
    onBeforeSend,
    onAdoptSession,
    onAppendTraceEvent,
    onSetStreamMessages,
    onSetStreamToolCards,
    onContextSnapshot,
    onLiveTurnStart,
    onLiveTurnEvent,
    onLiveTurnEnd,
    onLiveTurnStop,
    onTurnEnriched,
  } = args;

  const [composer, setComposerState] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [rememberMode, setRememberMode] = useState(false);
  const [queuedMessages, setQueuedMessages] = useState<string[]>([]);
  const [steeredMessages, setSteeredMessages] = useState<string[]>([]);
  const slashMenu = useComposerSlashMenu(composer);

  const queueRef = useRef<string[]>([]);
  const composingRef = useRef(false);
  const workerRunningRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const selectedSessionRef = useRef(selectedSessionId);
  const liveTurnRef = useRef<LiveTurnState | null>(null);
  selectedSessionRef.current = selectedSessionId;

  function setComposer(value: string) {
    setComposerState(value);
    if (isSlashPaletteOpen(value)) {
      slashMenu.resetSelection();
    }
  }

  function syncQueueView() {
    setQueuedMessages([...queueRef.current]);
  }

  function prepareOutgoingText(text: string): string {
    const trimmed = text.trim();
    if (!trimmed) return "";
    if (rememberMode || trimmed.startsWith("/remember ")) {
      setRememberMode(false);
      if (trimmed.startsWith("/remember ")) return trimmed;
      return `/remember ${trimmed}`;
    }
    return trimmed;
  }

  function applyTraceToLiveTurn(evt: TraceEventItem) {
    if (!liveTurnRef.current) return;
    liveTurnRef.current = reduceLiveTurn(liveTurnRef.current, evt);
    if (liveTurnRef.current && onLiveTurnEvent) {
      onLiveTurnEvent({ ...liveTurnRef.current });
    }
  }

  async function executeTurn(outgoing: string) {
    onBeforeSend();
    onSetStreamToolCards([]);
    const sessionAtStart = selectedSessionRef.current;
    const turn = createLiveTurn(outgoing);
    liveTurnRef.current = turn;
    onLiveTurnStart?.(turn);

    const path = selectedSessionRef.current
      ? `/api/sessions/${encodeURIComponent(selectedSessionRef.current)}/messages`
      : "/api/sessions";
    let donePayload: unknown = null;
    abortRef.current = new AbortController();
    try {
      await postSse(
        path,
        { message: outgoing },
        {
          onTrace: (payload) => {
            const evt = payload as TraceEventItem;
            onAppendTraceEvent(evt);
            applyTraceToLiveTurn(evt);
          },
          onReasoningDelta: (payload) => {
            if (!liveTurnRef.current) return;
            liveTurnRef.current = applyLiveTurnDelta(
              liveTurnRef.current,
              "reasoning",
              payload.text
            );
            if (liveTurnRef.current && onLiveTurnEvent) {
              onLiveTurnEvent({ ...liveTurnRef.current });
            }
          },
          onAssistantDelta: (payload) => {
            if (!liveTurnRef.current) return;
            liveTurnRef.current = applyLiveTurnDelta(
              liveTurnRef.current,
              "assistant",
              payload.text
            );
            if (liveTurnRef.current && onLiveTurnEvent) {
              onLiveTurnEvent({ ...liveTurnRef.current });
            }
          },
          onDone: (payload) => {
            donePayload = payload as TurnPayload;
          },
          onError: (message) => {
            setSendError(message);
          },
        },
        abortRef.current.signal
      );
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        liveTurnRef.current = stopLiveTurn(liveTurnRef.current);
        if (liveTurnRef.current && onLiveTurnEvent) {
          onLiveTurnEvent({ ...liveTurnRef.current });
        }
        onLiveTurnStop?.();
        liveTurnRef.current = null;
        throw err;
      }
      throw err;
    }

    const finalPayload = toTurnPayload(donePayload);
    if (finalPayload) {
      liveTurnRef.current = finalizeLiveTurn(liveTurnRef.current);
      if (liveTurnRef.current && onLiveTurnEvent) {
        onLiveTurnEvent({ ...liveTurnRef.current });
      }
      onSetStreamMessages(finalPayload.messages);
      onSetStreamToolCards(finalPayload.tool_cards || []);
      if (!sessionAtStart && finalPayload.session.id) {
        onAdoptSession(finalPayload.session.id);
      }
      if (onContextSnapshot && finalPayload.context_snapshot !== undefined) {
        onContextSnapshot(finalPayload.context_snapshot ?? null);
      }
      const terminal = findTerminalAssistantMessage(finalPayload.messages);
      if (terminal && liveTurnRef.current) {
        onTurnEnriched?.(
          terminal.id,
          enrichmentFromLiveTurn(
            liveTurnRef.current.thoughts,
            liveTurnRef.current.tools,
            finalPayload.tool_cards,
            terminal.reasoning_text
          )
        );
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sessions"] }),
        queryClient.invalidateQueries({ queryKey: ["session", finalPayload.session.id] }),
        queryClient.invalidateQueries({ queryKey: ["trace", finalPayload.session.id] }),
        queryClient.invalidateQueries({ queryKey: ["context", finalPayload.session.id] }),
      ]);
    }
    onLiveTurnEnd?.();
    liveTurnRef.current = null;
    setSteeredMessages([]);
  }

  async function worker() {
    if (workerRunningRef.current) return;
    workerRunningRef.current = true;
    setSending(true);
    setSendError(null);
    try {
      while (queueRef.current.length > 0) {
        const outgoing = queueRef.current.shift()!;
        syncQueueView();
        try {
          await executeTurn(outgoing);
        } catch (err) {
          if ((err as Error).name === "AbortError") {
            setSendError("已停止当前回合");
            break;
          }
          setSendError((err as Error).message);
          onLiveTurnEnd?.();
          liveTurnRef.current = null;
          break;
        }
      }
    } finally {
      workerRunningRef.current = false;
      abortRef.current = null;
      setSending(false);
      syncQueueView();
    }
  }

  async function submitSteer(outgoing: string) {
    const sessionId = selectedSessionRef.current;
    if (!sessionId) {
      enqueueOutgoing(outgoing);
      return;
    }
    try {
      await apiPost<{ ok: boolean; queued: number }>(
        `/api/sessions/${encodeURIComponent(sessionId)}/steer`,
        { message: outgoing }
      );
      setSteeredMessages((prev) => [...prev, outgoing]);
    } catch (err) {
      const message = (err as Error).message;
      if (message.includes("409") || /no active turn/i.test(message)) {
        enqueueOutgoing(outgoing);
        return;
      }
      setSendError(message);
    }
  }

  function enqueueOutgoing(outgoing: string) {
    queueRef.current.push(outgoing);
    syncQueueView();
    void worker();
  }

  function submitOutgoing(outgoing: string) {
    if (!outgoing) return;
    setComposerState("");
    if (sending) {
      void submitSteer(outgoing);
      return;
    }
    enqueueOutgoing(outgoing);
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    submitOutgoing(prepareOutgoingText(composer));
  }

  function onSend() {
    submitOutgoing(prepareOutgoingText(composer));
  }

  function sendCommand(command: string) {
    const outgoing = command.trim();
    if (!outgoing) return;
    if (sending) {
      void submitSteer(outgoing);
      return;
    }
    enqueueOutgoing(outgoing);
  }

  function onStop() {
    abortRef.current?.abort();
    queueRef.current = [];
    setSteeredMessages([]);
    syncQueueView();
  }

  function onCompositionStart(_e: CompositionEvent<HTMLTextAreaElement>) {
    composingRef.current = true;
  }

  function onCompositionEnd(_e: CompositionEvent<HTMLTextAreaElement>) {
    composingRef.current = false;
  }

  function pickSlashItem(insert: string) {
    setComposerState(insert);
  }

  function handleSlashKeyDown(e: KeyboardEvent<HTMLTextAreaElement>): boolean {
    if (!slashMenu.open) return false;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      slashMenu.moveSelection(1);
      return true;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      slashMenu.moveSelection(-1);
      return true;
    }
    if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
      const item = slashMenu.items[slashMenu.activeIndex];
      if (item) {
        e.preventDefault();
        pickSlashItem(item.insert);
        return true;
      }
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setComposerState("");
      return true;
    }
    return false;
  }

  function onComposerKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (handleSlashKeyDown(e)) return;
    const composing = composingRef.current || e.nativeEvent.isComposing;
    if (!shouldSubmitComposerOnEnter(e.key, e.shiftKey, composing)) {
      return;
    }
    e.preventDefault();
    if (composer.trim()) {
      submitOutgoing(prepareOutgoingText(composer));
    }
  }

  function toggleRememberMode() {
    const next = !rememberMode;
    setRememberMode(next);
    if (next && !composer.startsWith("/remember ")) {
      setComposerState((v) => (v.trim() ? `/remember ${v}` : "/remember "));
    }
  }

  return {
    composer,
    setComposer,
    sending,
    sendError,
    rememberMode,
    slashMenu,
    queuedMessages,
    steeredMessages,
    onSubmit,
    onSend,
    onStop,
    onComposerKeyDown,
    onCompositionStart,
    onCompositionEnd,
    toggleRememberMode,
    pickSlashItem,
    sendCommand,
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
    context_snapshot: raw.context_snapshot,
  };
}
