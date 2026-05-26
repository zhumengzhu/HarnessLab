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

function effortLabel(level: string, model?: ModelInfo): string {
  if (!level) return "";
  if (model?.backend === "deepseek") {
    if (level === "disabled") return "Off";
    if (level === "high") return "High";
    if (level === "max") return "Max";
    if (level === "enabled") return "High";
  }
  if (model?.thinking_schema === "toggle") {
    if (level === "disabled") return "Off";
    if (level === "enabled") return "Thinking";
  }
  if (level === "minimal") return "Minimal";
  return level.charAt(0).toUpperCase() + level.slice(1);
}

function effortSectionTitle(model: ModelInfo): string {
  if (model.backend === "deepseek") {
    return "Reasoning";
  }
  if (model.thinking_schema === "toggle") {
    return "Thinking";
  }
  return "Reasoning";
}

function formatContextLabel(m: ModelInfo): string {
  if (m.context_label && m.context_label !== "–") {
    return `${m.context_label} tokens`;
  }
  if (m.context_window > 0) {
    return `${Math.round(m.context_window / 1000)}K tokens`;
  }
  return "–";
}

function contextHint(m: ModelInfo): string {
  if (m.context_editable === false && m.context_window > 0) {
    return "Fixed by model · runtime uses full window";
  }
  return "";
}

function describeEffort(m: ModelInfo): string {
  if (m.current_effort) return effortLabel(m.current_effort, m);
  if (m.effort_levels.length > 0) return effortLabel(m.thinking_default, m);
  return "";
}

function modelSupportsEdit(m: ModelInfo): boolean {
  return m.effort_levels.length > 0;
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
                    {modelSupportsEdit(m) && (
                      <span className="model-sel-row-effort">
                        {effortLabel(m.current_effort || m.thinking_default, m)}
                      </span>
                    )}
                    {!m.configured && m.backend !== "simple" && (
                      <span className="model-sel-row-tag">no key</span>
                    )}
                    {m.current && <span className="model-sel-row-check">✓</span>}
                  </button>
                  {(isHovered || isEditing) && modelSupportsEdit(m) && (
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
              {modelSupportsEdit(editingModel) && (
                <div className="model-sel-section">
                  <div className="model-sel-section-title">
                    {effortSectionTitle(editingModel)}
                  </div>
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
                        <span>{effortLabel(lv, editingModel)}</span>
                        {active && <span className="model-sel-row-check">✓</span>}
                      </button>
                    );
                  })}
                </div>
              )}
              <div className="model-sel-section">
                <div className="model-sel-section-title">Context</div>
                <div className="model-sel-context-readonly">
                  {formatContextLabel(editingModel)}
                </div>
                {contextHint(editingModel) && (
                  <div className="model-sel-context-hint">{contextHint(editingModel)}</div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
