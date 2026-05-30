import type { HealthResponse } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { formatContextTokens } from "../chat/contextModalShared";

type RuntimeStatusCardProps = {
  health: HealthResponse | undefined;
  healthLoading: boolean;
  configPath?: string;
  displayCurrency?: string | null;
};

function RuntimeRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="settings-runtime-row">
      <span className="settings-runtime-label">{label}</span>
      <span className="settings-runtime-value" title={value}>
        {value}
      </span>
    </div>
  );
}

export function RuntimeStatusCard(props: RuntimeStatusCardProps) {
  const { health, healthLoading, configPath, displayCurrency } = props;
  const { t } = useI18n();

  const healthy = Boolean(health?.ok);
  const contextLabel =
    health?.runtime_context_tokens != null
      ? formatContextTokens(health.runtime_context_tokens)
      : "—";

  return (
    <article className="settings-card settings-runtime-card">
      <header className="settings-card-header">
        <span className="settings-card-icon" aria-hidden>
          ◉
        </span>
        <div>
          <h4 className="settings-card-title">{t("settings.runtimeCard")}</h4>
          <p className="settings-card-subtitle">{t("settings.runtimeCardHint")}</p>
        </div>
      </header>

      <div className="settings-runtime-rows">
        <div className="settings-runtime-row settings-runtime-row-status">
          <span className="settings-runtime-label">{t("settings.runtimeStatus")}</span>
          <span className={`settings-runtime-pill${healthy ? " ok" : " bad"}`}>
            <span className="settings-runtime-dot" aria-hidden />
            {healthy ? t("settings.runtimeHealthy") : t("settings.runtimeUnhealthy")}
          </span>
        </div>

        {healthLoading ? (
          <p className="settings-runtime-loading">{t("settings.runtimeLoading")}</p>
        ) : (
          <>
            <RuntimeRow
              label={t("settings.runtimeVersion")}
              value={health?.version ? `v${health.version}` : "—"}
            />
            <RuntimeRow
              label={t("settings.runtimeModel")}
              value={health?.model_label ?? health?.model ?? "—"}
            />
            <RuntimeRow label={t("settings.runtimeContext")} value={contextLabel} />
            {displayCurrency ? (
              <RuntimeRow label={t("settings.runtimeCurrency")} value={displayCurrency} />
            ) : null}
            <RuntimeRow
              label={t("settings.runtimePricing")}
              value={health?.pricing_version ?? "—"}
            />
            <RuntimeRow
              label={t("settings.runtimeWorkspace")}
              value={health?.workspace ?? "—"}
            />
            {health?.trace_path ? (
              <RuntimeRow label={t("settings.runtimeTrace")} value={health.trace_path} />
            ) : null}
            {configPath ? (
              <RuntimeRow label={t("settings.runtimeConfig")} value={configPath} />
            ) : null}
          </>
        )}
      </div>
    </article>
  );
}
