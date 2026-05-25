import type { FormEvent, KeyboardEvent } from "react";

type ComposerPanelProps = {
  composer: string;
  sending: boolean;
  sendError: string | null;
  rememberMode: boolean;
  skillMode: boolean;
  selectedSessionId: string | null;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onComposerChange: (value: string) => void;
  onToggleRememberMode: () => void;
  onToggleSkillMode: () => void;
  onComposerKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
};

export function ComposerPanel(props: ComposerPanelProps) {
  const {
    composer,
    sending,
    sendError,
    rememberMode,
    skillMode,
    selectedSessionId,
    onSubmit,
    onComposerChange,
    onToggleRememberMode,
    onToggleSkillMode,
    onComposerKeyDown,
  } = props;
  return (
    <section className="panel">
      <h2>Composer</h2>
      <div className="composer-quick-actions">
        <button
          type="button"
          className={rememberMode ? "active" : ""}
          disabled={sending}
          onClick={onToggleRememberMode}
        >
          记住{rememberMode ? " ✓" : ""}
        </button>
        <button
          type="button"
          className={skillMode ? "active" : ""}
          disabled={sending}
          onClick={onToggleSkillMode}
        >
          技能{skillMode ? " ✓" : ""}
        </button>
      </div>
      <form onSubmit={onSubmit} className="composer-form">
        <textarea
          value={composer}
          onChange={(e) => onComposerChange(e.target.value)}
          onKeyDown={onComposerKeyDown}
          rows={3}
          placeholder="输入消息（Enter 发送，Shift+Enter 换行）"
          disabled={sending}
        />
        <div className="composer-actions">
          <button type="submit" disabled={sending || !composer.trim()}>
            {sending ? "运行中..." : selectedSessionId ? "发送到当前会话" : "新建会话并发送"}
          </button>
          {rememberMode ? <span className="mode-chip">remember mode</span> : null}
          {skillMode ? <span className="mode-chip">skill mode</span> : null}
          {sendError ? <span className="error-text">{sendError}</span> : null}
        </div>
      </form>
    </section>
  );
}
