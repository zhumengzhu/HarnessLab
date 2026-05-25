import { useRef, useState } from "react";
import type { ModelInfo, ModelSwitchRequest } from "../../lib/schemas";

type ModelSelectorProps = {
  currentModelId: string | null;
  currentLabel: string;
  models: ModelInfo[];
  switching: boolean;
  switchError: string | null;
  onSwitch: (req: ModelSwitchRequest) => void;
  onDismissError: () => void;
};

function effortLabel(level: string): string {
  if (!level) return "";
  return level.charAt(0).toUpperCase() + level.slice(1);
}

function describeEffort(m: ModelInfo): string {
  if (m.current_effort) return effortLabel(m.current_effort);
  if (m.effort_levels.length > 0) return effortLabel(m.thinking_default);
  return "";
}

export function ModelSelector({
  currentModelId,
  currentLabel,
  models,
  switching,
  switchError,
  onSwitch,
  onDismissError,
}: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const current =
    models.find((m) => m.id === currentModelId) ?? models.find((m) => m.current);
  const effortTag = current ? describeEffort(current) : "";

  function close() {
    setOpen(false);
    setEditingId(null);
  }

  function handleRightClick(e: React.MouseEvent) {
    e.preventDefault();
    setOpen((v) => !v);
  }

  function pickModel(m: ModelInfo) {
    if (m.current) {
      close();
      return;
    }
    onSwitch({ model_id: m.id, backend: m.backend });
    close();
  }

  function applyEffort(m: ModelInfo, effort: string) {
    onSwitch({ model_id: m.id, backend: m.backend, effort });
    close();
  }

  const editingModel = editingId
    ? models.find((m) => m.id === editingId) ?? null
    : null;

  return (
    <div className="model-sel-wrap">
      <button
        ref={triggerRef}
        type="button"
        className={`model-sel-btn${switching ? " model-sel-busy" : ""}`}
        title="Click to choose a model — right-click for the same menu"
        onClick={() => setOpen((v) => !v)}
        onContextMenu={handleRightClick}
      >
        <span className="model-sel-icon">⊕</span>
        <span className="model-sel-label">{current?.label ?? currentLabel}</span>
        {effortTag && <span className="model-sel-effort">{effortTag}</span>}
        <span className="model-sel-caret">▾</span>
      </button>

      {switchError && (
        <div className="model-sel-error">
          <span>{switchError}</span>
          <button type="button" onClick={onDismissError}>×</button>
        </div>
      )}

      {open && (
        <div className="model-sel-flyout">
          <div className="model-sel-dropdown">
            <div className="model-sel-dropdown-header">Models</div>
            {models.map((m) => {
              const isHovered = hoverId === m.id;
              const isEditing = editingId === m.id;
              return (
                <div
                  key={m.id}
                  className={`model-sel-row${m.current ? " model-sel-row-current" : ""}${
                    !m.configured ? " model-sel-row-unconfigured" : ""
                  }${isEditing ? " model-sel-row-editing" : ""}`}
                  onMouseEnter={() => setHoverId(m.id)}
                  onMouseLeave={() => setHoverId((id) => (id === m.id ? null : id))}
                >
                  <button
                    type="button"
                    className="model-sel-row-pick"
                    title={!m.configured ? "API key not configured" : m.label}
                    disabled={!m.configured && m.backend !== "simple"}
                    onClick={() => pickModel(m)}
                  >
                    <span className="model-sel-row-label">{m.label}</span>
                    {m.effort_levels.length > 0 && (
                      <span className="model-sel-row-effort">
                        {effortLabel(m.current_effort || m.thinking_default)}
                      </span>
                    )}
                    {!m.configured && m.backend !== "simple" && (
                      <span className="model-sel-row-tag">no key</span>
                    )}
                    {m.current && <span className="model-sel-row-check">✓</span>}
                  </button>
                  {(isHovered || isEditing) && m.effort_levels.length > 0 && (
                    <button
                      type="button"
                      className="model-sel-row-edit"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingId(isEditing ? null : m.id);
                      }}
                    >
                      Edit
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {editingModel && (
            <div className="model-sel-flyout-sub">
              <div className="model-sel-dropdown-header">Options · {editingModel.label}</div>
              {editingModel.effort_levels.length > 0 && (
                <div className="model-sel-section">
                  <div className="model-sel-section-title">Reasoning</div>
                  {editingModel.effort_levels.map((lv) => {
                    const active =
                      (editingModel.current_effort || editingModel.thinking_default) === lv;
                    return (
                      <button
                        key={lv}
                        type="button"
                        className={`model-sel-effort-btn${active ? " model-sel-effort-active" : ""}`}
                        onClick={() => applyEffort(editingModel, lv)}
                      >
                        <span>{effortLabel(lv)}</span>
                        {active && <span className="model-sel-row-check">✓</span>}
                      </button>
                    );
                  })}
                </div>
              )}
              <div className="model-sel-section">
                <div className="model-sel-section-title">Context</div>
                <div className="model-sel-context-readonly">
                  {editingModel.context_window > 0
                    ? `${Math.round(editingModel.context_window / 1000)}K tokens`
                    : "–"}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
