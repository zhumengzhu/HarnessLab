import type { ReactNode } from "react";
import { useI18n } from "../../lib/i18n";
import { IconChevron } from "../shell/icons";
import { useChatScroll } from "./useChatScroll";

type ChatScrollAreaProps = {
  scrollSignal: string;
  resetKey?: string | null;
  children: ReactNode;
  onComposerChromeChange?: (collapsed: boolean) => void;
};

export function ChatScrollArea({
  scrollSignal,
  resetKey,
  children,
  onComposerChromeChange,
}: ChatScrollAreaProps) {
  const { t } = useI18n();
  const { scrollRef, bottomRef, newMessagesBelow, scrollToLatest, onScrollAreaScroll } =
    useChatScroll({ scrollSignal, resetKey, onComposerChromeChange });

  return (
    <div className="chat-scroll-column">
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
      </div>
      {newMessagesBelow ? (
        <button
          type="button"
          className="chat-new-messages"
          aria-label={t("chat.newMessages")}
          onClick={scrollToLatest}
        >
          <span className="chat-new-messages-icon" aria-hidden>
            <IconChevron size={14} open />
          </span>
          {t("chat.newMessages")}
        </button>
      ) : null}
    </div>
  );
}
