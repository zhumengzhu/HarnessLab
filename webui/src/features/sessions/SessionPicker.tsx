import { useRef, useState } from "react";
import type { SessionSummary } from "../../lib/schemas";

type SessionPickerProps = {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  sending: boolean;
  loading: boolean;
  error: string | null;
  onSelectSession: (id: string | null) => void;
  onForkCurrentSession: () => void;
  sessionActionError: string | null;
};

function sessionLabel(s: SessionSummary): string {
  return s.title?.trim() || s.goal?.trim() || s.id.slice(0, 8);
}

export function SessionPicker({
  sessions,
  selectedSessionId,
  sending,
  loading,
  error,
  onSelectSession,
  onForkCurrentSession,
  sessionActionError,
}: SessionPickerProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const current = sessions.find((s) => s.id === selectedSessionId);
  const currentTitle = current ? sessionLabel(current) : "新对话";

  function pick(id: string | null) {
    onSelectSession(id);
    setOpen(false);
  }

  return (
    <div className="session-picker" ref={wrapRef}>
      <button
        type="button"
        className="session-picker-new"
        title="新对话"
        disabled={sending}
        onClick={() => pick(null)}
      >
        +
      </button>

      <button
        type="button"
        className="session-picker-trigger"
        title="历史会话"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="session-picker-icon" aria-hidden>
          🕐
        </span>
        <span className="session-picker-title">{currentTitle}</span>
        <span className="session-picker-caret">▾</span>
      </button>

      {open && (
        <div className="session-picker-dropdown" role="listbox">
          <div className="session-picker-dropdown-header">Agents / Sessions</div>
          {sessionActionError ? (
            <p className="error-text session-picker-error">{sessionActionError}</p>
          ) : null}
          {loading ? <p className="session-picker-hint">Loading…</p> : null}
          {error ? <p className="error-text session-picker-error">{error}</p> : null}
          <ul className="session-picker-list">
            {sessions.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={selectedSessionId === s.id ? "active" : ""}
                  onClick={() => pick(s.id)}
                >
                  <strong>{sessionLabel(s)}</strong>
                  <small>
                    {s.status} · {s.message_count} msgs
                  </small>
                </button>
              </li>
            ))}
            {!loading && sessions.length === 0 ? (
              <li className="session-picker-hint">暂无历史会话</li>
            ) : null}
          </ul>
          {selectedSessionId ? (
            <div className="session-picker-footer">
              <button
                type="button"
                disabled={sending}
                onClick={() => {
                  onForkCurrentSession();
                  setOpen(false);
                }}
              >
                Fork 当前会话
              </button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
