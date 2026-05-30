import { useI18n } from "../../lib/i18n";

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
  const { t } = useI18n();

  if (sending) {
    return (
      <button
        type="button"
        className="composer-toolbar-btn composer-toolbar-btn-send composer-toolbar-btn-stop"
        title={t("chat.stopTurn")}
        aria-label={t("chat.stop")}
        onClick={onStop}
      >
        <span className="composer-action-stop-icon" aria-hidden />
      </button>
    );
  }

  return (
    <button
      type="button"
      className={`composer-toolbar-btn composer-toolbar-btn-send${
        canSend ? " composer-toolbar-btn-send-ready" : ""
      }`}
      title={t("chat.send")}
      aria-label={t("chat.send")}
      disabled={!canSend}
      onClick={onSend}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M14 2 7 9M14 2l-4.5 12L7 9 2 6.5 14 2z"
        />
      </svg>
    </button>
  );
}
