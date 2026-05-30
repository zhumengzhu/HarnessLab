import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "../../lib/api-client";
import { useI18n } from "../../lib/i18n";
import type { CheckpointPreviewResponse, CheckpointsResponse } from "../../lib/schemas";

type CheckpointPanelProps = {
  sessionId: string | null;
  onRewindSuccess?: () => void;
};

function shortId(id: string): string {
  if (id.length <= 14) return id;
  return `${id.slice(0, 10)}…`;
}

export function CheckpointPanel({ sessionId, onRewindSuccess }: CheckpointPanelProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["checkpoints", sessionId],
    enabled: Boolean(sessionId),
    queryFn: () =>
      apiGet<CheckpointsResponse>(`/api/sessions/${encodeURIComponent(sessionId || "")}/checkpoints`),
  });

  const previewQuery = useQuery({
    queryKey: ["checkpoint-preview", sessionId, selectedId],
    enabled: Boolean(sessionId && selectedId && confirmOpen),
    queryFn: () =>
      apiGet<CheckpointPreviewResponse>(
        `/api/sessions/${encodeURIComponent(sessionId || "")}/checkpoints/${encodeURIComponent(selectedId || "")}`
      ),
  });

  const rewindMutation = useMutation({
    mutationFn: async (checkpointId: string) =>
      apiPost<{ paths: string[] }>(
        `/api/sessions/${encodeURIComponent(sessionId || "")}/rewind`,
        {
          checkpoint_id: checkpointId,
          confirm: true,
        }
      ),
    onSuccess: (data) => {
      setActionMessage(t("checkpoint.restoredFiles", { count: data.paths.length }));
      setConfirmOpen(false);
      setSelectedId(null);
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["checkpoints", sessionId] });
      void queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      onRewindSuccess?.();
    },
    onError: (error: Error) => {
      setActionError(error.message);
    },
  });

  if (!sessionId) {
    return (
      <section className="checkpoint-panel-shell">
        <h3 className="checkpoint-panel-title">{t("checkpoint.title")}</h3>
        <p className="checkpoint-panel-hint">{t("checkpoint.hintNoSession")}</p>
      </section>
    );
  }

  const checkpoints = listQuery.data?.checkpoints ?? [];

  function openConfirm(checkpointId: string) {
    setSelectedId(checkpointId);
    setConfirmOpen(true);
    setActionError(null);
    setActionMessage(null);
  }

  function closeConfirm() {
    setConfirmOpen(false);
    setSelectedId(null);
  }

  return (
    <section className="checkpoint-panel-shell" aria-label={t("checkpoint.ariaLabel")}>
      <div className="checkpoint-panel-header">
        <h3 className="checkpoint-panel-title">{t("checkpoint.title")}</h3>
        <span className="checkpoint-panel-count">{checkpoints.length}</span>
      </div>
      <p className="checkpoint-panel-hint">{t("checkpoint.hint")}</p>

      {listQuery.isLoading ? <p className="checkpoint-panel-status">{t("common.loading")}</p> : null}
      {listQuery.error ? (
        <p className="error-text">{t("common.loadFailed", { error: (listQuery.error as Error).message })}</p>
      ) : null}
      {actionError ? <p className="error-text">{actionError}</p> : null}
      {actionMessage ? <p className="checkpoint-panel-success">{actionMessage}</p> : null}

      {!listQuery.isLoading && checkpoints.length === 0 ? (
        <p className="checkpoint-panel-empty">{t("checkpoint.empty")}</p>
      ) : null}

      {checkpoints.length ? (
        <ul className="checkpoint-list">
          {checkpoints.map((row) => (
            <li key={row.id} className="checkpoint-item">
              <div className="checkpoint-meta">
                <strong>{row.tool_name}</strong>
                <span>{new Date(row.created_at).toLocaleString()}</span>
                <code title={row.id}>{shortId(row.id)}</code>
              </div>
              <button type="button" className="checkpoint-rewind-btn" onClick={() => openConfirm(row.id)}>
                {t("checkpoint.rewind")}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {confirmOpen && selectedId ? (
        <div className="checkpoint-modal-backdrop" role="presentation" onClick={closeConfirm}>
          <div
            className="checkpoint-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="checkpoint-confirm-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h4 id="checkpoint-confirm-title">{t("checkpoint.confirmTitle")}</h4>
            <p className="checkpoint-panel-hint">{t("checkpoint.confirmHint")}</p>
            {previewQuery.isLoading ? (
              <p className="checkpoint-panel-status">{t("checkpoint.loadingDiff")}</p>
            ) : null}
            {previewQuery.error ? (
              <p className="error-text">{(previewQuery.error as Error).message}</p>
            ) : null}
            {previewQuery.data?.changes.length ? (
              <ul className="checkpoint-diff">
                {previewQuery.data.changes.map((change) => (
                  <li key={change.path} className="checkpoint-diff-row">
                    <div className="checkpoint-diff-path">{change.path}</div>
                    <div className="checkpoint-diff-cols">
                      <div className="checkpoint-diff-col">
                        <span className="checkpoint-diff-label">{t("checkpoint.currentWorkspace")}</span>
                        <pre>{change.current ?? t("checkpoint.fileMissing")}</pre>
                      </div>
                      <div className="checkpoint-diff-col">
                        <span className="checkpoint-diff-label">{t("checkpoint.afterRestore")}</span>
                        <pre>{change.restore_to ?? t("checkpoint.deleteFile")}</pre>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : previewQuery.data ? (
              <p className="checkpoint-panel-empty">{t("checkpoint.noDiff")}</p>
            ) : null}
            <div className="checkpoint-actions">
              <button
                type="button"
                className="checkpoint-confirm-btn"
                disabled={rewindMutation.isPending || previewQuery.isLoading}
                onClick={() => rewindMutation.mutate(selectedId)}
              >
                {rewindMutation.isPending ? t("checkpoint.confirming") : t("checkpoint.confirm")}
              </button>
              <button type="button" onClick={closeConfirm}>
                {t("checkpoint.cancel")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
