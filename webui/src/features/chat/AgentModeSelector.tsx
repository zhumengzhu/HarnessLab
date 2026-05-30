import { useState } from "react";
import { useI18n } from "../../lib/i18n";

export type AgentMode = "agent" | "plan" | "debug";

const MODES: { id: AgentMode; labelKey: "chat.agentModeAgent" | "chat.agentModePlan" | "chat.agentModeDebug"; available: boolean }[] = [
  { id: "agent", labelKey: "chat.agentModeAgent", available: true },
  { id: "plan", labelKey: "chat.agentModePlan", available: false },
  { id: "debug", labelKey: "chat.agentModeDebug", available: false },
];

type AgentModeSelectorProps = {
  mode: AgentMode;
  onChange: (mode: AgentMode) => void;
};

export function AgentModeSelector({ mode, onChange }: AgentModeSelectorProps) {
  const { t } = useI18n();
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
        title={t("chat.agentMode")}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="agent-mode-icon">∞</span>
        <span>{t(current.labelKey)}</span>
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
              title={!m.available ? t("chat.comingSoon", { label: t(m.labelKey) }) : t(m.labelKey)}
              disabled={!m.available}
              onClick={() => pick(m.id)}
            >
              <span>{t(m.labelKey)}</span>
              {mode === m.id && <span className="agent-mode-check">✓</span>}
              {!m.available ? <span className="agent-mode-soon">{t("chat.soon")}</span> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
