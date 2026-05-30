import { AgentModeSelector, type AgentMode } from "../chat/AgentModeSelector";
import { useI18n } from "../../lib/i18n";

type ComposerSettingsDrawerProps = {
  open: boolean;
  agentMode: AgentMode;
  rememberMode: boolean;
  onAgentModeChange: (mode: AgentMode) => void;
  onToggleRememberMode: () => void;
};

export function ComposerSettingsDrawer(props: ComposerSettingsDrawerProps) {
  const { open, agentMode, rememberMode, onAgentModeChange, onToggleRememberMode } = props;
  const { t } = useI18n();
  if (!open) return null;

  return (
    <div className="composer-settings-drawer">
      <div className="composer-settings-grid">
        <label className="composer-settings-field">
          <span>{t("chat.agentMode")}</span>
          <AgentModeSelector mode={agentMode} onChange={onAgentModeChange} />
        </label>
        <label className="composer-settings-field composer-settings-toggle">
          <span>{t("chat.rememberMode")}</span>
          <button
            type="button"
            className={rememberMode ? "active" : undefined}
            aria-pressed={rememberMode}
            onClick={onToggleRememberMode}
          >
            {rememberMode ? t("chat.rememberModeOn") : t("chat.rememberModeOff")}
          </button>
        </label>
      </div>
      <p className="composer-settings-hint">{t("chat.composerSettingsHint")}</p>
    </div>
  );
}
