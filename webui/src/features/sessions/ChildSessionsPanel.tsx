import type { SessionSummary } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { sessionLabel, sessionStatusLabel } from "../../lib/sessionLabels";

type ChildSessionsPanelProps = {
  parentSession: SessionSummary | null;
  childSessions: SessionSummary[];
  selectedSessionId: string | null;
  onSelectSession: (id: string) => void;
};

function shortGoal(session: SessionSummary, max = 56): string {
  const text = session.title?.trim() || session.goal.trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}

export function ChildSessionsPanel({
  parentSession,
  childSessions,
  selectedSessionId,
  onSelectSession,
}: ChildSessionsPanelProps) {
  const { t } = useI18n();

  if (!parentSession && childSessions.length === 0) {
    return null;
  }

  return (
    <section className="child-sessions-panel" aria-label={t("session.childSessions")}>
      {parentSession ? (
        <div className="child-sessions-parent">
          <span className="child-sessions-parent-label">{t("session.parentSession")}</span>
          <button
            type="button"
            className="child-sessions-parent-btn"
            onClick={() => onSelectSession(parentSession.id)}
          >
            ← {sessionLabel(parentSession)}
          </button>
        </div>
      ) : null}

      {childSessions.length ? (
        <div className="child-sessions-list-wrap">
          <div className="child-sessions-header">
            <span className="child-sessions-title">{t("session.childAgents")}</span>
            <span className="child-sessions-count">{childSessions.length}</span>
          </div>
          <ul className="child-sessions-list">
            {childSessions.map((child) => {
              const active = child.id === selectedSessionId;
              return (
                <li key={child.id}>
                  <button
                    type="button"
                    className={`child-sessions-item${active ? " child-sessions-item-active" : ""}`}
                    onClick={() => onSelectSession(child.id)}
                  >
                    <span className="child-sessions-item-title">{shortGoal(child)}</span>
                    <span className="child-sessions-item-meta">
                      {sessionStatusLabel(child.status)}
                      {child.step_count > 0
                        ? ` · ${t("session.stepsCount", { count: child.step_count })}`
                        : ""}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
