import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPatch } from "../../lib/api-client";
import type { PatchSessionResponse, SessionSummary } from "../../lib/schemas";
import { sessionListMeta, sessionLabel } from "../../lib/sessionLabels";
import { useI18n } from "../../lib/i18n";

const TITLE_MAX_LEN = 60;

type SessionListItemProps = {
  session: SessionSummary;
  selected: boolean;
  onSelect: () => void;
};

export function SessionListItem({ session, selected, onSelect }: SessionListItemProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(sessionLabel(session));
  const [renameError, setRenameError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) {
      setDraft(sessionLabel(session));
    }
  }, [session, editing]);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  function startEditing(event: React.MouseEvent) {
    event.stopPropagation();
    setRenameError(null);
    setDraft(sessionLabel(session));
    setEditing(true);
  }

  function cancelEditing() {
    setEditing(false);
    setRenameError(null);
    setDraft(sessionLabel(session));
  }

  async function saveTitle() {
    const title = draft.trim();
    if (!title) {
      setRenameError(t("session.titleEmpty"));
      return;
    }
    if (title.length > TITLE_MAX_LEN) {
      setRenameError(t("session.titleMaxLength", { max: TITLE_MAX_LEN }));
      return;
    }
    if (title === sessionLabel(session)) {
      setEditing(false);
      return;
    }

    setSaving(true);
    setRenameError(null);
    try {
      await apiPatch<PatchSessionResponse>(
        `/api/sessions/${encodeURIComponent(session.id)}`,
        { title }
      );
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      await queryClient.invalidateQueries({ queryKey: ["session", session.id] });
      setEditing(false);
    } catch (err) {
      setRenameError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <li className="app-session-list-item app-session-list-item-editing">
        <div className="app-session-rename">
          <input
            ref={inputRef}
            type="text"
            value={draft}
            maxLength={TITLE_MAX_LEN}
            disabled={saving}
            aria-label={t("session.renameSession")}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void saveTitle();
              }
              if (event.key === "Escape") {
                event.preventDefault();
                cancelEditing();
              }
            }}
            onBlur={() => {
              void saveTitle();
            }}
          />
          {renameError ? <small className="error-text">{renameError}</small> : null}
        </div>
      </li>
    );
  }

  return (
    <li className="app-session-list-item">
      <button
        type="button"
        className={selected ? "active" : ""}
        onClick={onSelect}
        onDoubleClick={startEditing}
      >
        <span className="app-session-list-title">
          <strong>{sessionLabel(session)}</strong>
          {selected ? (
            <button
              type="button"
              className="app-session-rename-trigger"
              title={t("common.rename")}
              aria-label={t("session.renameSession")}
              onClick={startEditing}
            >
              ✎
            </button>
          ) : null}
        </span>
        <small>{sessionListMeta(session)}</small>
      </button>
    </li>
  );
}
