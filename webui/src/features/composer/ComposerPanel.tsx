import { useState } from "react";
import type { CompositionEvent, FormEvent, KeyboardEvent } from "react";
import type { ContextSnapshot } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { ContextRing } from "../chat/ContextRing";
import { shouldSuggestCompaction } from "../chat/contextCompaction";
import type { AgentMode } from "../chat/AgentModeSelector";
import { DEFAULT_AGENT_PERSONA } from "../../lib/agentPersona";
import { ComposerSlashMenu } from "./ComposerSlashMenu";
import { ComposerSettingsDrawer } from "./ComposerSettingsDrawer";
import type { useComposerSlashMenu } from "./useComposerSlashMenu";
import { ComposerActionButton } from "./ComposerActionButton";
import { IconGear } from "../shell/icons";

type ComposerPanelProps = {
  composer: string;
  sending: boolean;
  sendError: string | null;
  queuedCount: number;
  steeredCount: number;
  rememberMode: boolean;
  slashMenu: ReturnType<typeof useComposerSlashMenu>;
  agentMode: AgentMode;
  onAgentModeChange: (m: AgentMode) => void;
  contextSnapshot: ContextSnapshot | null | undefined;
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
  agentName?: string;
  chromeCollapsed?: boolean;
};

export function ComposerPanel(props: ComposerPanelProps) {
  const {
    composer,
    sending,
    sendError,
    queuedCount,
    steeredCount,
    rememberMode,
    slashMenu,
    agentMode,
    onAgentModeChange,
    contextSnapshot,
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
    agentName = DEFAULT_AGENT_PERSONA.name,
    chromeCollapsed = false,
  } = props;

  const [settingsOpen, setSettingsOpen] = useState(false);
  const { t } = useI18n();
  const showCompact = Boolean(selectedSessionId) && shouldSuggestCompaction(contextSnapshot);

  return (
    <section className={`composer-card${chromeCollapsed ? " composer-card-compact" : ""}`}>
      <form onSubmit={onSubmit} className="composer-form composer-form-card">
        {(queuedCount > 0 || steeredCount > 0) && !chromeCollapsed ? (
          <div className="composer-queue-badges" aria-live="polite">
            {steeredCount > 0 ? (
              <span className="composer-queue-badge composer-queue-badge-steer">
                steer {steeredCount}
              </span>
            ) : null}
            {queuedCount > 0 ? (
              <span className="composer-queue-badge">queued {queuedCount}</span>
            ) : null}
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
            rows={1}
            placeholder={
              sending
                ? t("chat.sendSteerPlaceholder", { name: agentName })
                : t("chat.sendPlaceholder", { name: agentName })
            }
          />
        </div>

        {sendError ? <p className="error-text composer-error">{sendError}</p> : null}

        <ComposerSettingsDrawer
          open={settingsOpen && !chromeCollapsed}
          agentMode={agentMode}
          rememberMode={rememberMode}
          onAgentModeChange={onAgentModeChange}
          onToggleRememberMode={onToggleRememberMode}
        />

        <div className="composer-toolbar">
          <div className="composer-toolbar-left">
            {!chromeCollapsed ? (
              <button
                type="button"
                className={`composer-toolbar-btn${settingsOpen ? " active" : ""}`}
                title={t("chat.composerSettings")}
                aria-pressed={settingsOpen}
                aria-label={t("chat.composerSettings")}
                onClick={() => setSettingsOpen((open) => !open)}
              >
                <IconGear size={16} />
              </button>
            ) : null}
            {showCompact && !chromeCollapsed ? (
              <button
                type="button"
                className="composer-toolbar-btn composer-toolbar-text"
                onClick={onCompact}
              >
                Compact
              </button>
            ) : null}
            {rememberMode && !chromeCollapsed ? (
              <span className="composer-toolbar-badge">{t("chat.remember")}</span>
            ) : null}
          </div>
          <div className="composer-toolbar-right">
            {!chromeCollapsed ? <ContextRing snapshot={contextSnapshot} placement="inline" /> : null}
            <ComposerActionButton
              sending={sending}
              canSend={Boolean(composer.trim())}
              onSend={onSend}
              onStop={onStop}
            />
          </div>
        </div>
      </form>
    </section>
  );
}
