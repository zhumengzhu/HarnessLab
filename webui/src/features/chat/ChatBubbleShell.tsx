import type { ReactNode } from "react";
import { formatMessageTime, useI18n } from "../../lib/i18n";

type ChatBubbleShellProps = {
  role: "user" | "assistant";
  displayName: string;
  avatar: string;
  createdAt: string;
  children: ReactNode;
  footerExtra?: ReactNode;
  busy?: boolean;
  statusLabel?: string | null;
};

export function ChatBubbleShell(props: ChatBubbleShellProps) {
  const {
    role,
    displayName,
    avatar,
    createdAt,
    children,
    footerExtra,
    busy,
    statusLabel,
  } = props;
  const { locale } = useI18n();
  const timeLabel = formatMessageTime(createdAt, locale);
  const isUser = role === "user";

  return (
    <article className={`chat-bubble-row chat-bubble-row-${role}`} aria-busy={busy || undefined}>
      {!isUser ? (
        <div className="chat-bubble-avatar" aria-hidden>
          {avatar}
        </div>
      ) : null}

      <div className="chat-bubble-col">
        <div className={`chat-bubble${isUser ? " chat-bubble-user" : " chat-bubble-assistant"}`}>
          {children}
        </div>

        <div className={`chat-bubble-footer${isUser ? " chat-bubble-footer-user" : ""}`}>
          <div className="chat-bubble-meta">
            <span className="chat-bubble-name">{displayName}</span>
            <span className="chat-bubble-sep">·</span>
            <time className="chat-bubble-time" dateTime={createdAt}>
              {timeLabel}
            </time>
            {statusLabel ? (
              <>
                <span className="chat-bubble-sep">·</span>
                <span className="chat-bubble-status">{statusLabel}</span>
              </>
            ) : null}
          </div>
          {footerExtra}
        </div>
      </div>

      {isUser ? (
        <div className="chat-bubble-avatar chat-bubble-avatar-user" aria-hidden>
          {avatar}
        </div>
      ) : null}
    </article>
  );
}
