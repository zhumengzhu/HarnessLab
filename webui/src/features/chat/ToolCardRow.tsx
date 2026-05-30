import type { ToolCard } from "../../lib/schemas";
import type { ActivityDisplayMode } from "./chatDisplay";

type ToolCardRowProps = {
  card: ToolCard;
  displayMode: ActivityDisplayMode;
  defaultOpen?: boolean;
};

function toolSummary(card: ToolCard): string {
  const parts = [card.tool || "tool", card.ok ? "ok" : "error"];
  if (card.duration_ms != null) {
    parts.push(`${card.duration_ms}ms`);
  }
  return parts.join(" · ");
}

export function ToolCardRow({ card, displayMode, defaultOpen = false }: ToolCardRowProps) {
  const summary = toolSummary(card);
  const body = card.error || card.output_preview || "";

  if (displayMode === "compact") {
    if (!body.trim()) {
      return <div className="chat-msg-tool chat-msg-tool-compact chat-msg-tool-static">{summary}</div>;
    }
    return (
      <details className="chat-msg-tool chat-msg-tool-compact">
        <summary>{summary}</summary>
        <pre>{body}</pre>
      </details>
    );
  }

  return (
    <details className="chat-msg-tool" open={defaultOpen}>
      <summary>{summary}</summary>
      <pre>{body}</pre>
    </details>
  );
}
