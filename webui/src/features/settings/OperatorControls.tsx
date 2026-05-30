import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../../lib/api-client";
import { useI18n } from "../../lib/i18n";

type OperatorControlsProps = {
  multiAgentEnabled: boolean;
  failoverEnabled: boolean;
  fallbacks: string[];
};

export function OperatorControls(props: OperatorControlsProps) {
  const { multiAgentEnabled, failoverEnabled, fallbacks } = props;
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggleMultiAgent(next: boolean) {
    setPending(true);
    setNote(null);
    setError(null);
    try {
      const result = await apiPost<{
        ok: boolean;
        multi_agent_enabled: boolean;
        message?: string;
      }>("/api/settings/multi-agent", { enabled: next });
      setNote(result.message ?? t("settings.savedRestartHint"));
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(false);
    }
  }

  const failoverChain = fallbacks.length ? fallbacks.join(" → ") : t("settings.noFallbacks");

  return (
    <details className="settings-section settings-operator" open>
      <summary>{t("settings.operatorControls")}</summary>
      <div className="settings-operator-row">
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={multiAgentEnabled}
            disabled={pending}
            onChange={(e) => void toggleMultiAgent(e.target.checked)}
          />
          <span>{t("settings.multiAgent")}</span>
        </label>
        <p className="settings-mcp-hint">{t("settings.multiAgentHint")}</p>
      </div>
      <div className="settings-operator-row">
        <strong>{t("settings.providerFailover")}</strong>
        <p className="settings-mcp-hint">
          {failoverEnabled
            ? t("settings.failoverEnabled", { chain: failoverChain })
            : t("settings.failoverDisabled")}
        </p>
      </div>
      {note ? <p className="skills-status">{note}</p> : null}
      {error ? <p className="error-text">{t("common.loadFailed", { error })}</p> : null}
    </details>
  );
}
