import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../../lib/i18n";

export type CommandPaletteAction = {
  id: string;
  label: string;
  hint?: string;
  group: string;
  run: () => void;
};

type CommandPaletteProps = {
  open: boolean;
  onClose: () => void;
  actions: CommandPaletteAction[];
};

export function CommandPalette({ open, onClose, actions }: CommandPaletteProps) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter(
      (action) =>
        action.label.toLowerCase().includes(q) ||
        action.group.toLowerCase().includes(q) ||
        action.hint?.toLowerCase().includes(q)
    );
  }, [actions, query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveIndex(0);
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((idx) => Math.min(idx + 1, Math.max(filtered.length - 1, 0)));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((idx) => Math.max(idx - 1, 0));
        return;
      }
      if (event.key === "Enter" && filtered[activeIndex]) {
        event.preventDefault();
        filtered[activeIndex].run();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, filtered, activeIndex, onClose]);

  if (!open) return null;

  return (
    <div className="command-palette-backdrop" role="presentation" onClick={onClose}>
      <div
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-label={t("command.title")}
        onClick={(event) => event.stopPropagation()}
      >
        <input
          autoFocus
          className="command-palette-input"
          placeholder={t("command.placeholder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <ul className="command-palette-list" role="listbox">
          {filtered.length === 0 ? (
            <li className="command-palette-empty">{t("command.empty")}</li>
          ) : (
            filtered.map((action, index) => (
              <li key={action.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={index === activeIndex}
                  className={index === activeIndex ? "active" : undefined}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => {
                    action.run();
                    onClose();
                  }}
                >
                  <span className="command-palette-label">{action.label}</span>
                  <span className="command-palette-meta">
                    {action.hint ? `${action.group} · ${action.hint}` : action.group}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}

export function useCommandPaletteShortcut(onOpen: () => void, enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const isMac = navigator.platform.toLowerCase().includes("mac");
      const mod = isMac ? event.metaKey : event.ctrlKey;
      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpen();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled, onOpen]);
}
