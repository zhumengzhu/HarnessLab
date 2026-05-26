import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "../../lib/api-client";

type CheckpointSummary = {
  id: string;
  session_id: string;
  tool_name: string;
  created_at: string;
};

type CheckpointPreview = {
  session_id: string;
  checkpoint: {
    id: string;
    tool_name: string;
    tool_args: Record<string, unknown>;
    created_at: string;
  };
  changes: Array<{
    path: string;
    current: string | null;
    restore_to: string | null;
  }>;
};

type CheckpointPanelProps = {
  sessionId: string | null;
};

export function CheckpointPanel({ sessionId }: CheckpointPanelProps) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["checkpoints", sessionId],
    enabled: Boolean(sessionId),
    queryFn: () =>
      apiGet<{ checkpoints: CheckpointSummary[] }>(
        `/api/sessions/${sessionId}/checkpoints`
      ),
  });

  const previewQuery = useQuery({
    queryKey: ["checkpoint-preview", sessionId, selectedId],
    enabled: Boolean(sessionId && selectedId && confirmOpen),
    queryFn: () =>
      apiGet<CheckpointPreview>(`/api/sessions/${sessionId}/checkpoints/${selectedId}`),
  });

  const rewindMutation = useMutation({
    mutationFn: async (checkpointId: string) =>
      apiPost<{ paths: string[] }>(`/api/sessions/${sessionId}/rewind`, {
        checkpoint_id: checkpointId,
        confirm: true,
      }),
    onSuccess: (data) => {
      setActionMessage(`已恢复 ${data.paths.length} 个文件。`);
      setConfirmOpen(false);
      setSelectedId(null);
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["checkpoints", sessionId] });
    },
    onError: (error: Error) => {
      setActionError(error.message);
    },
  });

  if (!sessionId) return null;

  const checkpoints = listQuery.data?.checkpoints ?? [];

  return (
    <details className="diag-block checkpoint-panel">
      <summary>Checkpoints / Rewind</summary>
      {listQuery.isLoading ? <p>Loading checkpoints…</p> : null}
      {listQuery.error ? (
        <p className="error-text">Failed: {(listQuery.error as Error).message}</p>
      ) : null}
      {actionError ? <p className="error-text">{actionError}</p> : null}
      {actionMessage ? <p className="settings-mcp-hint">{actionMessage}</p> : null}

      {!listQuery.isLoading && checkpoints.length === 0 ? (
        <p className="settings-mcp-hint">此会话尚无 checkpoint（在 mutating tool 执行前自动创建）。</p>
      ) : null}

      {checkpoints.length ? (
        <ul className="checkpoint-list">
          {checkpoints.map((row) => (
            <li key={row.id} className="checkpoint-item">
              <div className="checkpoint-meta">
                <strong>{row.tool_name}</strong>
                <span>{new Date(row.created_at).toLocaleString()}</span>
                <code>{row.id}</code>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedId(row.id);
                  setConfirmOpen(true);
                  setActionError(null);
                  setActionMessage(null);
                }}
              >
                Rewind…
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {confirmOpen && selectedId ? (
        <div className="checkpoint-confirm" role="dialog" aria-modal="true">
          <h4>确认 Rewind</h4>
          {previewQuery.isLoading ? <p>Loading diff…</p> : null}
          {previewQuery.error ? (
            <p className="error-text">{(previewQuery.error as Error).message}</p>
          ) : null}
          {previewQuery.data?.changes.length ? (
            <ul className="checkpoint-diff">
              {previewQuery.data.changes.map((change) => (
                <li key={change.path}>
                  <strong>{change.path}</strong>
                  <pre>{change.current ?? "(missing)"}</pre>
                  <pre>{change.restore_to ?? "(delete file)"}</pre>
                </li>
              ))}
            </ul>
          ) : previewQuery.data ? (
            <p className="settings-mcp-hint">与当前 workspace 无差异。</p>
          ) : null}
          <div className="checkpoint-actions">
            <button
              type="button"
              disabled={rewindMutation.isPending}
              onClick={() => rewindMutation.mutate(selectedId)}
            >
              确认恢复
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirmOpen(false);
                setSelectedId(null);
              }}
            >
              取消
            </button>
          </div>
        </div>
      ) : null}
    </details>
  );
}
