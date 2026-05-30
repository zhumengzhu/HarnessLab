import { useMemo } from "react";
import type { SettingsResponse, HealthResponse } from "../../lib/schemas";
import { JsonHighlight, settingsToJson5Text } from "../../lib/jsonHighlight";
import { OperatorControls } from "./OperatorControls";
import { UiPreferencesPanel } from "./UiPreferencesPanel";
import { RuntimeStatusCard } from "./RuntimeStatusCard";
import { DeveloperPanel } from "./DeveloperPanel";
import { useI18n } from "../../lib/i18n";
import type { ActivityDisplayMode, ChatTextSize } from "../chat/chatDisplay";
import type { ThemeFamily, ThemePreference } from "../shell/theme";
import type { Locale } from "../../lib/i18n";

type SettingsPanelProps = {
  loading: boolean;
  error: string | null;
  data: SettingsResponse | undefined;
  health: HealthResponse | undefined;
  healthLoading: boolean;
  themeFamily: ThemeFamily;
  onThemeFamilyChange: (family: ThemeFamily) => void;
  themePreference: ThemePreference;
  onThemePreferenceChange: (theme: ThemePreference) => void;
  locale: Locale;
  onLocaleChange: (locale: Locale) => void;
  activityDisplay: ActivityDisplayMode;
  onActivityDisplayChange: (mode: ActivityDisplayMode) => void;
  chatTextSize: ChatTextSize;
  onChatTextSizeChange: (size: ChatTextSize) => void;
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
  const { t } = useI18n();
  const configured = Array.isArray(servers) ? servers.length : 0;
  if (!configured && !health) return null;

  const entries = health ? Object.entries(health) : [];

  return (
    <details className="settings-section settings-mcp-health" open>
      <summary>{t("settings.mcpServers")}</summary>
      <p className="settings-mcp-hint">{t("settings.mcpHint")}</p>
      {!configured ? (
        <p className="settings-mcp-empty">{t("settings.mcpNotConfigured")}</p>
      ) : entries.length ? (
        <ul className="settings-mcp-list">
          {entries.map(([name, row]) => (
            <li key={name} className={`settings-mcp-item settings-mcp-row-${row.status}`}>
              <span className="settings-mcp-name">{name}</span>
              <span className="settings-mcp-status">{row.status}</span>
              <span className="settings-mcp-tools">{t("settings.mcpToolsCount", { count: row.tools })}</span>
              {row.error ? <code className="settings-mcp-error">{row.error}</code> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="settings-mcp-empty">{t("settings.mcpConfiguredNoHealth", { count: configured })}</p>
      )}
    </details>
  );
}

export function SettingsPanel(props: SettingsPanelProps) {
  const {
    loading,
    error,
    data,
    health,
    healthLoading,
    themeFamily,
    onThemeFamilyChange,
    themePreference,
    onThemePreferenceChange,
    locale,
    onLocaleChange,
    activityDisplay,
    onActivityDisplayChange,
    chatTextSize,
    onChatTextSizeChange,
  } = props;
  const { t } = useI18n();
  const settings = data?.settings;
  const configSource = data?.config_source;
  const sections = useMemo(() => buildSections(settings), [settings]);
  const mcpHealth = settings?.mcp_health as Record<string, McpHealthEntry> | undefined;
  const budget = settings?.budget as { display_currency?: string } | undefined;

  const fullJson5 = useMemo(() => {
    if (configSource?.trim()) return configSource;
    return settings ? settingsToJson5Text(settings) : "";
  }, [configSource, settings]);

  return (
    <section className="panel settings-panel">
      <div className="panel-title-row">
        <div>
          <h2>{t("settings.title")}</h2>
          <p className="settings-subtitle">
            {t("settings.subtitle")}
            <code>{String(settings?.config_path ?? "~/.config/harnesslab/config.json")}</code>
          </p>
        </div>
      </div>

      {loading ? <p>{t("common.loading")}</p> : null}
      {error ? <p className="error-text">{t("common.loadFailed", { error })}</p> : null}

      <UiPreferencesPanel
        themeFamily={themeFamily}
        onThemeFamilyChange={onThemeFamilyChange}
        themePreference={themePreference}
        onThemePreferenceChange={onThemePreferenceChange}
        locale={locale}
        onLocaleChange={onLocaleChange}
        activityDisplay={activityDisplay}
        onActivityDisplayChange={onActivityDisplayChange}
        chatTextSize={chatTextSize}
        onChatTextSizeChange={onChatTextSizeChange}
      />

      {!loading && !error ? (
        <div className="settings-card-grid settings-runtime-grid">
          <RuntimeStatusCard
            health={health}
            healthLoading={healthLoading}
            configPath={String(settings?.config_path ?? "~/.config/harnesslab/config.json")}
            displayCurrency={budget?.display_currency ?? null}
          />
        </div>
      ) : null}

      {!loading && !error && settings ? (
        <>
          <details className="settings-full-json" open>
            <summary>
              {configSource?.trim() ? t("settings.fullConfigDisk") : t("settings.fullConfigView")}
            </summary>
            <JsonHighlight source={fullJson5} />
          </details>

          <OperatorControls
            multiAgentEnabled={Boolean(settings.multi_agent_enabled)}
            failoverEnabled={Boolean(settings.model_failover_enabled)}
            fallbacks={Array.isArray(settings.model_fallbacks) ? (settings.model_fallbacks as string[]) : []}
          />

          <McpHealthPanel servers={settings.mcp_servers} health={mcpHealth} />

          <DeveloperPanel health={health} />

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
