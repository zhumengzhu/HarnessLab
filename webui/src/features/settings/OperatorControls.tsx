import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../../lib/api-client";
import { useI18n } from "../../lib/i18n";

const FAILOVER_BACKENDS = ["simple", "deepseek", "anthropic", "openai", "gemini"] as const;

type OperatorControlsProps = {
  multiAgentEnabled: boolean;
  failoverEnabled: boolean;
  fallbacks: string[];
  modelBackend: string;
  failoverChain?: string[];
};

export function OperatorControls(props: OperatorControlsProps) {
  const {
    multiAgentEnabled,
    failoverEnabled,
    fallbacks,
    modelBackend,
    failoverChain = [],
  } = props;
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [failoverOn, setFailoverOn] = useState(failoverEnabled);
  const [selectedFallbacks, setSelectedFallbacks] = useState<string[]>(fallbacks);

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

  async function saveFailover() {
    setPending(true);
    setNote(null);
    setError(null);
    try {
      const result = await apiPost<{
        ok: boolean;
        model_failover_enabled: boolean;
        model_failover_chain?: string[];
        message?: string;
      }>("/api/settings/failover", {
        enabled: failoverOn,
        fallbacks: selectedFallbacks.filter((b) => b !== modelBackend),
      });
      const chain = result.model_failover_chain?.join(" → ") ?? "";
      setNote(result.message ?? t("settings.failoverSaved", { chain }));
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(false);
    }
  }

  function toggleFallback(backend: string) {
    setSelectedFallbacks((prev) =>
      prev.includes(backend) ? prev.filter((b) => b !== backend) : [...prev, backend]
    );
  }

  const activeChain =
    failoverChain.length > 0
      ? failoverChain.join(" → ")
      : fallbacks.length
        ? `${modelBackend} → ${fallbacks.join(" → ")}`
        : modelBackend;

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
            ? t("settings.failoverEnabled", { chain: activeChain })
            : t("settings.failoverDisabledHint")}
        </p>
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={failoverOn}
            disabled={pending}
            onChange={(e) => setFailoverOn(e.target.checked)}
          />
          <span>{t("settings.failoverToggle")}</span>
        </label>
        <fieldset className="settings-failover-backends" disabled={pending || !failoverOn}>
          <legend>{t("settings.failoverFallbacks")}</legend>
          {FAILOVER_BACKENDS.filter((b) => b !== modelBackend).map((backend) => (
            <label key={backend} className="settings-failover-option">
              <input
                type="checkbox"
                checked={selectedFallbacks.includes(backend)}
                onChange={() => toggleFallback(backend)}
              />
              <span>{backend}</span>
            </label>
          ))}
        </fieldset>
        <button
          type="button"
          className="settings-save-btn"
          disabled={pending}
          onClick={() => void saveFailover()}
        >
          {t("settings.failoverSave")}
        </button>
      </div>
      {note ? <p className="skills-status">{note}</p> : null}
      {error ? <p className="error-text">{t("common.loadFailed", { error })}</p> : null}
    </details>
  );
}
