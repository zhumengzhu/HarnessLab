export type AgentMode = "agent" | "plan" | "debug";

const MODES: { id: AgentMode; label: string; available: boolean }[] = [
  { id: "agent", label: "Agent", available: true },
  { id: "plan", label: "Plan", available: false },
  { id: "debug", label: "Debug", available: false },
];

type AgentModeSelectorProps = {
  mode: AgentMode;
  onChange: (mode: AgentMode) => void;
};

export function AgentModeSelector({ mode, onChange }: AgentModeSelectorProps) {
  return (
    <div className="agent-mode-wrap">
      {MODES.map((m) => (
        <button
          key={m.id}
          type="button"
          className={`agent-mode-btn${mode === m.id ? " agent-mode-active" : ""}${
            !m.available ? " agent-mode-unavailable" : ""
          }`}
          title={!m.available ? `${m.label} mode — coming soon` : `${m.label} mode`}
          onClick={() => m.available && onChange(m.id)}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
