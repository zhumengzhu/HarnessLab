import { useState } from "react";
import { apiGet } from "../../lib/api-client";
import type { ArtifactResponse } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";

type ToolSpanInspectorProps = {
  metrics: Record<string, unknown>;
  toolName?: string;
  sessionId?: string;
};

export function ToolSpanInspector({ metrics, toolName, sessionId }: ToolSpanInspectorProps) {
  const { t } = useI18n();
  const args = metrics.args;
  const preview =
    typeof metrics.output_preview === "string" ? metrics.output_preview : null;
  const error = typeof metrics.error === "string" ? metrics.error : null;
  const truncated = metrics.output_truncated === true;
  const outputSize =
    typeof metrics.output_size === "number" ? metrics.output_size : null;
  const artifactRef =
    typeof metrics.artifact_ref === "string" ? metrics.artifact_ref : null;

  const [artifactContent, setArtifactContent] = useState<string | null>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  async function loadArtifact() {
    if (!artifactRef || !sessionId) return;
    setArtifactLoading(true);
    setArtifactError(null);
    try {
      const payload = await apiGet<ArtifactResponse>(
        `/api/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(artifactRef)}`
      );
      if (payload.encoding === "base64") {
        setArtifactContent(`[binary ${payload.mime}, ${payload.size_bytes} bytes]`);
      } else {
        setArtifactContent(payload.content);
      }
    } catch (err) {
      setArtifactError(err instanceof Error ? err.message : String(err));
    } finally {
      setArtifactLoading(false);
    }
  }

  if (args == null && !preview && !error) return null;

  return (
    <div className="trace-tool-inspector">
      {toolName ? <div className="trace-inspector-meta">tool: {toolName}</div> : null}
      {args != null ? (
        <details className="trace-inspector-section" open>
          <summary>Arguments</summary>
          <pre>{JSON.stringify(args, null, 2)}</pre>
        </details>
      ) : null}
      {preview ? (
        <details className="trace-inspector-section" open>
          <summary>
            Output
            {outputSize != null ? ` (${outputSize.toLocaleString()} bytes` : ""}
            {truncated ? ", truncated" : ""}
            {outputSize != null ? ")" : ""}
          </summary>
          <pre>{preview}</pre>
          {artifactRef ? (
            <div className="trace-tool-artifact">
              <code>{artifactRef}</code>
              {sessionId ? (
                <button
                  type="button"
                  className="trace-artifact-load"
                  disabled={artifactLoading}
                  onClick={() => void loadArtifact()}
                >
                  {artifactLoading
                    ? t("trace.artifactLoading")
                    : t("trace.artifactLoad")}
                </button>
              ) : null}
              {artifactError ? <p className="error-text">{artifactError}</p> : null}
              {artifactContent ? <pre className="trace-artifact-body">{artifactContent}</pre> : null}
            </div>
          ) : null}
        </details>
      ) : null}
      {error ? (
        <details className="trace-inspector-section">
          <summary>Error</summary>
          <pre>{error}</pre>
        </details>
      ) : null}
    </div>
  );
}
