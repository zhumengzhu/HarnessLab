import { useMemo } from "react";
import type { SettingsResponse } from "../../lib/schemas";
import { JsonHighlight, settingsToJson5Text } from "../../lib/jsonHighlight";
import { OperatorControls } from "./OperatorControls";

type SettingsPanelProps = {
  loading: boolean;
  error: string | null;
  data: SettingsResponse | undefined;
};

type SettingsSection = {
  id: string;
  title: string;
  hint?: string;
  value: unknown;
};

function buildSections(settings: Record<string, unknown> | undefined): SettingsSection[] {
  if (!settings) return [];
  const order = [
    "model_backend",
    "model",
    "serve",
    "policy",
    "tools",
    "loop",
    "limits",
    "workspace_root",
  ];
  const skip = new Set(["mcp_health"]);
  const sections: SettingsSection[] = [];
  const seen = new Set<string>();

  for (const key of order) {
    if (!(key in settings) || skip.has(key)) continue;
    sections.push({
      id: key,
      title: key.replace(/_/g, " "),
      value: settings[key],
    });
    seen.add(key);
  }

  for (const [key, value] of Object.entries(settings)) {
    if (seen.has(key) || skip.has(key)) continue;
    sections.push({ id: key, title: key.replace(/_/g, " "), value });
  }

  return sections;
}

type McpHealthEntry = {
  status: string;
  tools: number;
  error: string | null;
};

function McpHealthPanel({
  servers,
  health,
}: {
  servers: unknown;
  health: Record<string, McpHealthEntry> | undefined;
}) {
  const configured = Array.isArray(servers) ? servers.length : 0;
  if (!configured && !health) return null;

  const entries = health ? Object.entries(health) : [];

  return (
    <details className="settings-section settings-mcp-health" open>
      <summary>MCP servers</summary>
      <p className="settings-mcp-hint">
        MCP 已支持（Phase 5.4）：在 <code>config.json</code> 的{" "}
        <code>tools.mcp_servers</code> 配置 stdio 服务后，启动时注册为{" "}
        <code>mcp_*</code> 工具。下方为最近一次启动探测结果。
      </p>
      {!configured ? (
        <p className="settings-mcp-empty">未配置 MCP server。</p>
      ) : entries.length ? (
        <ul className="settings-mcp-list">
          {entries.map(([name, row]) => (
            <li key={name} className={`settings-mcp-item settings-mcp-row-${row.status}`}>
              <span className="settings-mcp-name">{name}</span>
              <span className="settings-mcp-status">{row.status}</span>
              <span className="settings-mcp-tools">{row.tools} tools</span>
              {row.error ? <code className="settings-mcp-error">{row.error}</code> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="settings-mcp-empty">已配置 {configured} 个 server，暂无 health 快照。</p>
      )}
    </details>
  );
}

export function SettingsPanel(props: SettingsPanelProps) {
  const { loading, error, data } = props;
  const settings = data?.settings;
  const configSource = data?.config_source;
  const sections = useMemo(() => buildSections(settings), [settings]);
  const mcpHealth = settings?.mcp_health as Record<string, McpHealthEntry> | undefined;

  const fullJson5 = useMemo(() => {
    if (configSource?.trim()) return configSource;
    return settings ? settingsToJson5Text(settings) : "";
  }, [configSource, settings]);

  return (
    <section className="panel settings-panel">
      <div className="panel-title-row">
        <div>
          <h2>Settings</h2>
          <p className="settings-subtitle">
            运行时快照（只读）。配置文件支持 JSON5（注释、尾逗号）：
            <code>{String(settings?.config_path ?? "~/.config/harnesslab/config.json")}</code>
          </p>
        </div>
      </div>

      {loading ? <p>Loading…</p> : null}
      {error ? <p className="error-text">Failed: {error}</p> : null}

      {!loading && !error && settings ? (
        <>
          <details className="settings-full-json" open>
            <summary>
              {configSource?.trim() ? "磁盘配置文件（JSON5）" : "完整配置（JSON5 视图）"}
            </summary>
            <JsonHighlight source={fullJson5} />
          </details>

          <OperatorControls
            multiAgentEnabled={Boolean(settings.multi_agent_enabled)}
            failoverEnabled={Boolean(settings.model_failover_enabled)}
            fallbacks={Array.isArray(settings.model_fallbacks) ? (settings.model_fallbacks as string[]) : []}
          />

          <McpHealthPanel servers={settings.mcp_servers} health={mcpHealth} />

          <div className="settings-sections">
            {sections.map((sec) => {
              const sectionText = settingsToJson5Text({ [sec.id]: sec.value }).replace(/^\{\n|\n\}$/g, "");
              return (
                <details key={sec.id} className="settings-section">
                  <summary>{sec.title}</summary>
                  <JsonHighlight source={sectionText} />
                </details>
              );
            })}
          </div>
        </>
      ) : null}
    </section>
  );
}
