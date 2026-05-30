import type { CompositionEvent, FormEvent, KeyboardEvent } from "react";
import type { ContextSnapshot, ModelInfo, ModelSwitchRequest } from "../../lib/schemas";
import { ChatToolbar } from "../chat/ChatToolbar";
import type { AgentMode } from "../chat/AgentModeSelector";
import { ComposerSlashMenu } from "./ComposerSlashMenu";
import type { useComposerSlashMenu } from "./useComposerSlashMenu";

type ComposerPanelProps = {
  composer: string;
  sending: boolean;
  sendError: string | null;
  queuedMessages: string[];
  steeredMessages: string[];
  rememberMode: boolean;
  slashMenu: ReturnType<typeof useComposerSlashMenu>;
  agentMode: AgentMode;
  onAgentModeChange: (m: AgentMode) => void;
  currentModelId: string | null;
  currentLabel: string;
  models: ModelInfo[];
  modelSwitching: boolean;
  modelSwitchError: string | null;
  contextSnapshot: ContextSnapshot | null | undefined;
  onModelSwitch: (req: ModelSwitchRequest) => void;
  onDismissModelError: () => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onSend: () => void;
  onStop: () => void;
  onComposerChange: (value: string) => void;
  onToggleRememberMode: () => void;
  onPickSlashItem: (insert: string) => void;
  onComposerKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  onCompositionStart: (e: CompositionEvent<HTMLTextAreaElement>) => void;
  onCompositionEnd: (e: CompositionEvent<HTMLTextAreaElement>) => void;
  selectedSessionId: string | null;
  onCompact: () => void;
  chromeCollapsed?: boolean;
};

function queuePreview(text: string, max = 48): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (oneLine.length <= max) return oneLine;
  return `${oneLine.slice(0, max)}…`;
}

export function ComposerPanel(props: ComposerPanelProps) {
  const {
    composer,
    sending,
    sendError,
    queuedMessages,
    steeredMessages,
    rememberMode,
    slashMenu,
    agentMode,
    onAgentModeChange,
    currentModelId,
    currentLabel,
    models,
    modelSwitching,
    modelSwitchError,
    contextSnapshot,
    onModelSwitch,
    onDismissModelError,
    onSubmit,
    onSend,
    onStop,
    onComposerChange,
    onToggleRememberMode,
    onPickSlashItem,
    onComposerKeyDown,
    onCompositionStart,
    onCompositionEnd,
    selectedSessionId,
    onCompact,
    chromeCollapsed = false,
  } = props;

  return (
    <section className={`panel composer-panel${chromeCollapsed ? " composer-panel-compact" : ""}`}>
      <form onSubmit={onSubmit} className="composer-form">
        <div className="composer-quick-actions">
          <button
            type="button"
            className={rememberMode ? "active" : ""}
            onClick={onToggleRememberMode}
          >
            记住{rememberMode ? " ✓" : ""}
          </button>
          {rememberMode ? <span className="mode-chip">remember</span> : null}
        </div>

        {steeredMessages.length > 0 ? (
          <div className="composer-queue composer-steer-queue" aria-live="polite">
            <span className="composer-queue-label">Steer {steeredMessages.length}</span>
            <ul className="composer-queue-list">
              {steeredMessages.map((msg, idx) => (
                <li key={`steer-${idx}-${msg.slice(0, 12)}`}>{queuePreview(msg)}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {queuedMessages.length > 0 ? (
          <div className="composer-queue" aria-live="polite">
            <span className="composer-queue-label">下一回合 {queuedMessages.length}</span>
            <ul className="composer-queue-list">
              {queuedMessages.map((msg, idx) => (
                <li key={`${idx}-${msg.slice(0, 12)}`}>{queuePreview(msg)}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="composer-input-wrap">
          <ComposerSlashMenu
            open={slashMenu.open}
            items={slashMenu.items}
            activeIndex={slashMenu.activeIndex}
            onPick={(item) => onPickSlashItem(item.insert)}
          />
          <textarea
            value={composer}
            onChange={(e) => onComposerChange(e.target.value)}
            onCompositionStart={onCompositionStart}
            onCompositionEnd={onCompositionEnd}
            onKeyDown={onComposerKeyDown}
            rows={3}
            placeholder={
              sending
                ? "Agent 运行中 — Enter 注入 steer（当前 turn），Shift+Enter 换行"
                : "Plan, Build, / 唤起命令或技能…（Enter 发送，Shift+Enter 换行）"
            }
          />
        </div>

        {sendError ? <p className="error-text composer-error">{sendError}</p> : null}

        <ChatToolbar
          agentMode={agentMode}
          onAgentModeChange={onAgentModeChange}
          currentModelId={currentModelId}
          currentLabel={currentLabel}
          models={models}
          modelSwitching={modelSwitching}
          modelSwitchError={modelSwitchError}
          contextSnapshot={contextSnapshot}
          sending={sending}
          canSend={Boolean(composer.trim())}
          onModelSwitch={onModelSwitch}
          onDismissModelError={onDismissModelError}
          onSend={onSend}
          onStop={onStop}
          onCompact={selectedSessionId ? onCompact : undefined}
          compactDisabled={sending}
        />
      </form>
    </section>
  );
}
