import { useState } from "react";

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
  const [open, setOpen] = useState(false);
  const current = MODES.find((m) => m.id === mode) ?? MODES[0];

  function pick(next: AgentMode) {
    const entry = MODES.find((m) => m.id === next);
    if (entry?.available) {
      onChange(next);
      setOpen(false);
    }
  }

  return (
    <div className="agent-mode-wrap">
      <button
        type="button"
        className="agent-mode-trigger"
        title="Agent mode"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="agent-mode-icon">∞</span>
        <span>{current.label}</span>
        <span className="agent-mode-caret">▾</span>
      </button>

      {open && (
        <div className="agent-mode-dropdown">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`agent-mode-option${mode === m.id ? " agent-mode-option-active" : ""}${
                !m.available ? " agent-mode-option-disabled" : ""
              }`}
              title={!m.available ? `${m.label} — coming soon` : m.label}
              disabled={!m.available}
              onClick={() => pick(m.id)}
            >
              <span>{m.label}</span>
              {mode === m.id && <span className="agent-mode-check">✓</span>}
              {!m.available ? <span className="agent-mode-soon">soon</span> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
