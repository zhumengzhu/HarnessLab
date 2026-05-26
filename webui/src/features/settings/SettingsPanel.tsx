import { useMemo } from "react";
import type { SettingsResponse } from "../../lib/schemas";
import { JsonHighlight, settingsToJson5Text } from "../../lib/jsonHighlight";

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
  const sections: SettingsSection[] = [];
  const seen = new Set<string>();

  for (const key of order) {
    if (!(key in settings)) continue;
    sections.push({
      id: key,
      title: key.replace(/_/g, " "),
      value: settings[key],
    });
    seen.add(key);
  }

  for (const [key, value] of Object.entries(settings)) {
    if (seen.has(key)) continue;
    sections.push({ id: key, title: key.replace(/_/g, " "), value });
  }

  return sections;
}

export function SettingsPanel(props: SettingsPanelProps) {
  const { loading, error, data } = props;
  const settings = data?.settings;
  const configSource = data?.config_source;
  const sections = useMemo(() => buildSections(settings), [settings]);

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
