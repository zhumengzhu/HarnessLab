import type { MessageItem, ToolCard } from "./schemas";
import type { ThoughtEntry } from "../features/live-turn/liveTurnReducer";
import { mergeMessageReasoningIntoThoughts } from "./thoughtUtils";

export type MessageVisibilityPrefs = {
  showThinking: boolean;
  showTools: boolean;
};

export function parseThoughtBlocks(content: string): { thought: string | null; body: string } {
  const open = content.indexOf("<thinking>");
  const close = content.indexOf("</thinking>");
  if (open === -1 || close === -1 || close <= open) {
    return { thought: null, body: content };
  }
  const thought = content.slice(open + "<thinking>".length, close).trim();
  const body = (content.slice(0, open) + content.slice(close + "</thinking>".length)).trim();
  return { thought: thought || null, body };
}

export function resolvePersistedThoughts(
  message: MessageItem,
  thoughtEntries?: ThoughtEntry[]
): ThoughtEntry[] {
  const { thought: inlineThought } =
    message.role === "assistant"
      ? parseThoughtBlocks(message.content)
      : { thought: null as string | null };

  const merged = mergeMessageReasoningIntoThoughts(
    thoughtEntries ?? [],
    message.reasoning_text,
    message.created_at
  );
  if (merged.length) return merged;
  if (inlineThought) {
    return [
      {
        stepIndex: 0,
        status: "done",
        text: inlineThought,
        startedAt: new Date(message.created_at).getTime(),
      },
    ];
  }
  return [];
}

export function assistantDisplayBody(message: MessageItem): string {
  if (message.role !== "assistant") return message.content.trim();
  const { body } = parseThoughtBlocks(message.content);
  return body.trim();
}

export function hasVisibleThoughts(thoughts: ThoughtEntry[]): boolean {
  return thoughts.some((thought) => Boolean(thought.text?.trim()));
}

export function isChatMessageVisible(
  message: MessageItem,
  prefs: MessageVisibilityPrefs,
  enrichment?: { thoughts?: ThoughtEntry[]; tools?: ToolCard[] }
): boolean {
  if (message.role === "user") {
    return Boolean(message.content.trim());
  }

  if (message.role !== "assistant") {
    return Boolean(message.content.trim());
  }

  if (assistantDisplayBody(message)) {
    return true;
  }

  const thoughts = resolvePersistedThoughts(message, enrichment?.thoughts);
  if (prefs.showThinking && hasVisibleThoughts(thoughts)) {
    return true;
  }

  const tools = enrichment?.tools ?? [];
  if (prefs.showTools && tools.length > 0) {
    return true;
  }

  return false;
}

export function isLiveTurnVisible(
  turn: {
    assistantText: string;
    thoughts: ThoughtEntry[];
    tools: unknown[];
    childRuns: unknown[];
    phase: string;
    thinkingLikely?: boolean;
  },
  prefs: MessageVisibilityPrefs
): boolean {
  if (turn.assistantText.trim()) {
    return true;
  }

  if (turn.childRuns.length > 0) {
    return true;
  }

  if (prefs.showThinking) {
    if (hasVisibleThoughts(turn.thoughts)) {
      return true;
    }
    if (
      (turn.phase === "running" || turn.phase === "pending") &&
      turn.thinkingLikely &&
      turn.thoughts.every((item) => item.status !== "thinking")
    ) {
      return true;
    }
  }

  if (prefs.showTools && turn.tools.length > 0) {
    return true;
  }

  if (turn.phase === "running" || turn.phase === "pending") {
    return false;
  }

  return false;
}
