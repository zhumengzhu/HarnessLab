import type { ContextSnapshot, ModelInfo, ModelSwitchRequest } from "../../lib/schemas";
import { ComposerActionButton } from "../composer/ComposerActionButton";
import { AgentModeSelector, type AgentMode } from "./AgentModeSelector";
import { ContextRing } from "./ContextRing";
import { shouldSuggestCompaction } from "./contextCompaction";
import { ModelSelector } from "./ModelSelector";

type ChatToolbarProps = {
  agentMode: AgentMode;
  onAgentModeChange: (m: AgentMode) => void;
  currentModelId: string | null;
  currentLabel: string;
  models: ModelInfo[];
  modelSwitching: boolean;
  modelSwitchError: string | null;
  contextSnapshot: ContextSnapshot | null | undefined;
  sending: boolean;
  canSend: boolean;
  onModelSwitch: (req: ModelSwitchRequest) => void;
  onDismissModelError: () => void;
  onSend: () => void;
  onStop: () => void;
  onCompact?: () => void;
  compactSuggested?: boolean;
  compactDisabled?: boolean;
};

export function ChatToolbar(props: ChatToolbarProps) {
  const {
    agentMode,
    onAgentModeChange,
    currentModelId,
    currentLabel,
    models,
    modelSwitching,
    modelSwitchError,
    contextSnapshot,
    sending,
    canSend,
    onModelSwitch,
    onDismissModelError,
    onSend,
    onStop,
    onCompact,
    compactSuggested,
    compactDisabled,
  } = props;

  const showCompact =
    Boolean(onCompact) &&
    (compactSuggested ?? shouldSuggestCompaction(contextSnapshot));

  return (
    <div className="chat-toolbar">
      <div className="chat-toolbar-left">
        <AgentModeSelector mode={agentMode} onChange={onAgentModeChange} />
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
      <div className="chat-toolbar-right">
        {showCompact ? (
          <button
            type="button"
            className="chat-compact-btn"
            title="压缩上下文（/compact）"
            disabled={compactDisabled}
            onClick={onCompact}
          >
            Compact
          </button>
        ) : null}
        <ContextRing snapshot={contextSnapshot} />
        <ComposerActionButton
          sending={sending}
          canSend={canSend}
          onSend={onSend}
          onStop={onStop}
        />
      </div>
    </div>
  );
}
