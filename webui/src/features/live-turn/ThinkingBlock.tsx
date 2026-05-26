import { useEffect, useState } from "react";
import { MarkdownView } from "../../lib/MarkdownView";
import type { ThoughtEntry } from "./liveTurnReducer";

type ThinkingBlockProps = {
  thought: ThoughtEntry;
  showWhenIdle?: boolean;
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.max(1, Math.round(ms))}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function ThinkingBlock({ thought, showWhenIdle }: ThinkingBlockProps) {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (thought.status !== "thinking") return;
    const tick = () => setElapsedMs(Date.now() - thought.startedAt);
    tick();
    const id = window.setInterval(tick, 200);
    return () => window.clearInterval(id);
  }, [thought.startedAt, thought.status]);

  if (thought.status === "thinking") {
    if (thought.text?.trim()) {
      return (
        <details className="thinking-block thinking-block-active" open>
          <summary aria-live="polite">
            <span className="thinking-pulse" aria-hidden />
            Thinking…
            <span className="thinking-elapsed">{formatDuration(elapsedMs)}</span>
          </summary>
          <div className="thinking-block-body">
            <MarkdownView markdown={thought.text} />
          </div>
        </details>
      );
    }
    return (
      <div className="thinking-block thinking-block-active" aria-live="polite">
        <span className="thinking-pulse" aria-hidden />
        Thinking…
        <span className="thinking-elapsed">{formatDuration(elapsedMs)}</span>
      </div>
    );
  }

  const duration = thought.durationMs ?? elapsedMs;
  const durationLabel =
    duration > 0 ? `Thought for ${formatDuration(duration)}` : "Thought";

  if (!thought.text?.trim()) {
    return null;
  }

  if (!showWhenIdle && duration <= 0) {
    return null;
  }

  return (
    <details className="thinking-block thinking-block-done">
      <summary>{durationLabel}</summary>
      {thought.text ? (
        <div className="thinking-block-body">
          <MarkdownView markdown={thought.text} />
        </div>
      ) : null}
    </details>
  );
}
