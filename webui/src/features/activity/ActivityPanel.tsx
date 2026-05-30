import { useState } from "react";
import { useI18n } from "../../lib/i18n";
import type { ActivityEntry } from "./activityFeed";

type ActivityPanelProps = {
  entries: ActivityEntry[];
  live: boolean;
  onClear: () => void;
  fullPage?: boolean;
};

export function ActivityPanel({ entries, live, onClear, fullPage = false }: ActivityPanelProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(true);

  if (!fullPage && entries.length === 0 && !live) {
    return null;
  }

  const list = (
    <ul className="activity-panel-list">
      {entries.length === 0 ? <li className="activity-panel-empty">{t("activity.waiting")}</li> : null}
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
  );

  if (fullPage) {
    return (
      <section className="activity-panel activity-panel-full" aria-live="polite">
        <header className="activity-panel-header">
          <div className="activity-panel-title">
            {t("activity.title")}
            <span className="activity-panel-count">{entries.length}</span>
            {live ? <span className="activity-panel-live">{t("activity.live")}</span> : null}
          </div>
          <button
            type="button"
            className="activity-panel-clear"
            onClick={onClear}
            disabled={!entries.length}
          >
            {t("activity.clear")}
          </button>
        </header>
        {list}
      </section>
    );
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
          {t("activity.title")}
          <span className="activity-panel-count">{entries.length}</span>
          {live ? <span className="activity-panel-live">{t("activity.live")}</span> : null}
        </button>
        <button type="button" className="activity-panel-clear" onClick={onClear} disabled={!entries.length}>
          {t("activity.clear")}
        </button>
      </header>

      {open ? list : null}
    </section>
  );
}
