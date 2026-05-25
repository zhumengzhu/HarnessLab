import type { ContextSnapshot, ModelInfo, ModelSwitchRequest } from "../../lib/schemas";
import { AgentModeSelector, type AgentMode } from "./AgentModeSelector";
import { ModelSelector } from "./ModelSelector";
import { ContextRing } from "./ContextRing";

type ChatToolbarProps = {
  agentMode: AgentMode;
  onAgentModeChange: (m: AgentMode) => void;
  currentModelId: string | null;
  currentLabel: string;
  models: ModelInfo[];
  modelSwitching: boolean;
  modelSwitchError: string | null;
  onModelSwitch: (req: ModelSwitchRequest) => void;
  onDismissModelError: () => void;
  contextSnapshot: ContextSnapshot | null | undefined;
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
    onModelSwitch,
    onDismissModelError,
    contextSnapshot,
  } = props;

  return (
    <div className="chat-toolbar">
      <AgentModeSelector mode={agentMode} onChange={onAgentModeChange} />
      <div className="chat-toolbar-right">
        <ModelSelector
          currentModelId={currentModelId}
          currentLabel={currentLabel}
          models={models}
          switching={modelSwitching}
          switchError={modelSwitchError}
          onSwitch={onModelSwitch}
          onDismissError={onDismissModelError}
        />
        <ContextRing snapshot={contextSnapshot} />
      </div>
    </div>
  );
}
