import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../../lib/api-client";

type OperatorControlsProps = {
  multiAgentEnabled: boolean;
  failoverEnabled: boolean;
  fallbacks: string[];
};

export function OperatorControls(props: OperatorControlsProps) {
  const { multiAgentEnabled, failoverEnabled, fallbacks } = props;
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
      setNote(result.message ?? "Saved. Restart ./hl-serve to apply spawn_sub_agent.");
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(false);
    }
  }

  return (
    <details className="settings-section settings-operator" open>
      <summary>Operator controls</summary>
      <div className="settings-operator-row">
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={multiAgentEnabled}
            disabled={pending}
            onChange={(e) => void toggleMultiAgent(e.target.checked)}
          />
          <span>Multi-agent (spawn_sub_agent)</span>
        </label>
        <p className="settings-mcp-hint">
          写入 <code>config.json</code> 的 <code>loop.multi_agent.enabled</code>。
          注册工具需重启 serve。
        </p>
      </div>
      <div className="settings-operator-row">
        <strong>Provider failover</strong>
        <p className="settings-mcp-hint">
          {failoverEnabled
            ? `Enabled · chain: ${fallbacks.length ? fallbacks.join(" → ") : "(no fallbacks configured)"}`
            : "Disabled — set model.failover_enabled in config to enable P6 chain."}
        </p>
      </div>
      {note ? <p className="skills-status">{note}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
    </details>
  );
}
