type ComposerActionButtonProps = {
  sending: boolean;
  canSend: boolean;
  onSend: () => void;
  onStop: () => void;
};

export function ComposerActionButton({
  sending,
  canSend,
  onSend,
  onStop,
}: ComposerActionButtonProps) {
  if (sending) {
    return (
      <button
        type="button"
        className="composer-action-btn composer-action-stop"
        title="停止当前回合"
        aria-label="Stop"
        onClick={onStop}
      >
        <span className="composer-action-stop-icon" aria-hidden />
      </button>
    );
  }

  return (
    <button
      type="button"
      className="composer-action-btn composer-action-send"
      title="发送"
      aria-label="Send"
      disabled={!canSend}
      onClick={onSend}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M8 12V4M8 4L5 7M8 4l3 3"
        />
      </svg>
    </button>
  );
}
