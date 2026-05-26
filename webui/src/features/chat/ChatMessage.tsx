import { useMemo } from "react";
import type { MessageItem, ToolCard } from "../../lib/schemas";
import { MarkdownView } from "../../lib/MarkdownView";
import { mergeMessageReasoningIntoThoughts } from "../../lib/thoughtUtils";
import { ThinkingBlock } from "../live-turn/ThinkingBlock";
import type { ThoughtEntry } from "../live-turn/liveTurnReducer";

type ChatMessageProps = {
  message: MessageItem;
  toolCards?: ToolCard[];
  /** Advanced tool/debug rows: collapsible via native disclosure. */
  defaultCollapsed?: boolean;
  thoughtEntries?: ThoughtEntry[];
};

function previewLine(text: string, max = 72): string {
  const line = text.split("\n").find((l) => l.trim())?.trim() ?? "";
  if (line.length <= max) return line;
  return `${line.slice(0, max)}…`;
}

function parseThoughtBlocks(content: string): { thought: string | null; body: string } {
  const open = content.indexOf("<thinking>");
  const close = content.indexOf("</thinking>");
  if (open === -1 || close === -1 || close <= open) {
    return { thought: null, body: content };
  }
  const thought = content.slice(open + "<thinking>".length, close).trim();
  const body = (content.slice(0, open) + content.slice(close + "</thinking>".length)).trim();
  return { thought: thought || null, body };
}

function MessageBody({
  displayBody,
  fallbackContent,
  persistedThoughts,
  toolCards,
}: {
  displayBody: string;
  fallbackContent: string;
  persistedThoughts: ThoughtEntry[];
  toolCards: ToolCard[];
}) {
  return (
    <div className="chat-msg-body">
      {persistedThoughts.map((thought, idx) => (
        <ThinkingBlock key={idx} thought={thought} showWhenIdle />
      ))}

      {toolCards.length > 0 ? (
        <div className="chat-msg-tools">
          {toolCards.map((card, idx) => (
            <details key={`${card.tool}-${idx}`} className="chat-msg-tool">
              <summary>
                {card.tool || "tool"} · {card.ok ? "ok" : "error"}
                {card.duration_ms != null ? ` · ${card.duration_ms}ms` : ""}
              </summary>
              <pre>{card.error || card.output_preview || ""}</pre>
            </details>
          ))}
        </div>
      ) : null}

      <MarkdownView markdown={displayBody || fallbackContent} className="chat-msg-content" />
    </div>
  );
}

export function ChatMessage({
  message,
  toolCards = [],
  defaultCollapsed,
  thoughtEntries,
}: ChatMessageProps) {
  const { thought: inlineThought, body } = useMemo(
    () =>
      message.role === "assistant"
        ? parseThoughtBlocks(message.content)
        : { thought: null, body: message.content },
    [message.content, message.role]
  );

  const persistedThoughts = useMemo(() => {
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
          status: "done" as const,
          text: inlineThought,
          startedAt: new Date(message.created_at).getTime(),
        },
      ];
    }
    return [];
  }, [thoughtEntries, inlineThought, message.created_at, message.reasoning_text]);

  const roleLabel =
    message.role === "user"
      ? "You"
      : message.role === "assistant"
        ? "Assistant"
        : message.role === "tool"
          ? "Tool"
          : message.role;

  const displayBody = body || message.content;
  const bodyProps = {
    displayBody,
    fallbackContent: message.content,
    persistedThoughts,
    toolCards,
  };

  if (defaultCollapsed) {
    return (
      <details className={`chat-msg chat-msg-${message.role} chat-msg-disclosure`}>
        <summary className="chat-msg-summary">
          <span className="chat-msg-role">{roleLabel}</span>
          <span className="chat-msg-preview">{previewLine(displayBody || message.content)}</span>
        </summary>
        <MessageBody {...bodyProps} />
      </details>
    );
  }

  return (
    <article className={`chat-msg chat-msg-${message.role}`}>
      <div className="chat-msg-header chat-msg-header-static">
        <span className="chat-msg-role">{roleLabel}</span>
      </div>
      <MessageBody {...bodyProps} />
    </article>
  );
}
