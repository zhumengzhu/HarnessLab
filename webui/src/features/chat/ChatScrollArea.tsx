import type { ReactNode } from "react";
import { useChatScroll } from "./useChatScroll";

type ChatScrollAreaProps = {
  scrollSignal: string;
  children: ReactNode;
  onComposerChromeChange?: (collapsed: boolean) => void;
};

export function ChatScrollArea({
  scrollSignal,
  children,
  onComposerChromeChange,
}: ChatScrollAreaProps) {
  const { scrollRef, bottomRef, showJumpToLatest, scrollToLatest, onScrollAreaScroll } =
    useChatScroll({ scrollSignal, onComposerChromeChange });

  return (
    <div className="chat-scroll-host">
      <div
        ref={scrollRef}
        className="chat-scroll-area"
        onScroll={onScrollAreaScroll}
        data-testid="chat-scroll-area"
      >
        {children}
        <div ref={bottomRef} className="chat-scroll-bottom" aria-hidden />
      </div>
      {showJumpToLatest ? (
        <button
          type="button"
          className="chat-jump-latest"
          aria-label="跳到最新"
          title="跳到最新"
          onClick={scrollToLatest}
        >
          ↓ 最新
        </button>
      ) : null}
    </div>
  );
}
