import type { ReactNode } from "react";
import type { ModelInfo, ModelSwitchRequest, SessionSummary } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { ModelSelector } from "./ModelSelector";
import { IconBrain, IconFocus, IconRefresh, IconWrench } from "../shell/icons";

type ChatSessionHeaderProps = {
  session: SessionSummary | null;
  sessionId: string | null;
  currentModelId: string | null;
  currentLabel: string;
  models: ModelInfo[];
  modelSwitching: boolean;
  modelSwitchError: string | null;
  showThinking: boolean;
  showTools: boolean;
  focusMode: boolean;
  onModelSwitch: (req: ModelSwitchRequest) => void;
  onDismissModelError: () => void;
  onToggleThinking: () => void;
  onToggleTools: () => void;
  onToggleFocus: () => void;
  onRefresh: () => void;
};

function shortSessionId(id: string): string {
  if (id.length <= 16) return id;
  return `${id.slice(0, 10)}…${id.slice(-4)}`;
}

export function ChatSessionHeader(props: ChatSessionHeaderProps) {
  const {
    session,
    sessionId,
    currentModelId,
    currentLabel,
    models,
    modelSwitching,
    modelSwitchError,
    showThinking,
    showTools,
    focusMode,
    onModelSwitch,
    onDismissModelError,
    onToggleThinking,
    onToggleTools,
    onToggleFocus,
    onRefresh,
  } = props;
  const { t } = useI18n();

  return (
    <div className="chat-session-header">
      <div className="chat-session-header-chips">
        {sessionId ? (
          <SessionKeyChip
            label={session?.title || shortSessionId(sessionId)}
            sessionId={sessionId}
            copyLabel={t("session.copySessionId")}
          />
        ) : null}

        <div className="session-header-model">
          <ModelSelector
            currentModelId={currentModelId}
            currentLabel={currentLabel}
            models={models}
            switching={modelSwitching}
            switchError={modelSwitchError}
            onSwitch={onModelSwitch}
            onDismissError={onDismissModelError}
          />
        </div>
      </div>

      <div
        className="chat-session-header-toggles"
        role="toolbar"
        aria-label={t("session.toolbar")}
      >
        <HeaderToggle
          label={t("session.thinking")}
          active={showThinking}
          onClick={onToggleThinking}
          icon={<IconBrain size={17} />}
        />
        <HeaderToggle
          label={t("session.tools")}
          active={showTools}
          onClick={onToggleTools}
          icon={<IconWrench size={17} />}
        />
        <HeaderToggle
          label={t("session.focus")}
          active={focusMode}
          onClick={onToggleFocus}
          icon={<IconFocus size={17} />}
        />
        <HeaderToggle
          label={t("session.refresh")}
          onClick={onRefresh}
          icon={<IconRefresh size={17} />}
        />
      </div>
    </div>
  );
}

function SessionKeyChip({
  label,
  sessionId,
  copyLabel,
}: {
  label: string;
  sessionId: string;
  copyLabel: string;
}) {
  return (
    <button
      type="button"
      className="session-header-chip session-header-key"
      title={`${sessionId} (${copyLabel})`}
      onClick={() => {
        void navigator.clipboard?.writeText(sessionId);
      }}
    >
      {label}
    </button>
  );
}

function HeaderToggle(props: {
  label: string;
  active?: boolean;
  onClick: () => void;
  icon: ReactNode;
}) {
  const { label, active, onClick, icon } = props;
  return (
    <button
      type="button"
      className={`session-header-toggle${active ? " active" : ""}`}
      aria-pressed={active}
      title={label}
      onClick={onClick}
    >
      {icon}
    </button>
  );
}
