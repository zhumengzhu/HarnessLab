import { useState } from "react";
import type { ActivityEntry } from "./activityFeed";

type ActivityPanelProps = {
  entries: ActivityEntry[];
  live: boolean;
  onClear: () => void;
};

export function ActivityPanel({ entries, live, onClear }: ActivityPanelProps) {
  const [open, setOpen] = useState(true);

  if (entries.length === 0 && !live) {
    return null;
  }

  return (
    <section className={`activity-panel${open ? " activity-panel-open" : ""}`} aria-live="polite">
      <header className="activity-panel-header">
        <button
          type="button"
          className="activity-panel-toggle"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          Activity
          <span className="activity-panel-count">{entries.length}</span>
          {live ? <span className="activity-panel-live">live</span> : null}
        </button>
        <button type="button" className="activity-panel-clear" onClick={onClear} disabled={!entries.length}>
          清空
        </button>
      </header>

      {open ? (
        <ul className="activity-panel-list">
          {entries.length === 0 ? <li className="activity-panel-empty">等待活动…</li> : null}
          {entries.map((entry) => (
            <li
              key={entry.id}
              className={`activity-panel-item activity-panel-item-${entry.kind}${
                entry.ok === false ? " activity-panel-item-error" : ""
              }`}
            >
              <strong>{entry.label}</strong>
              {entry.detail ? <span>{entry.detail}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
