import { useMemo, useState } from "react";
import type { HealthResponse } from "../../lib/schemas";
import { copyText } from "../../lib/copyText";
import { useI18n } from "../../lib/i18n";

type DeveloperPanelProps = {
  health: HealthResponse | undefined;
};

type DevItem = {
  id: string;
  label: string;
  value: string;
  hint?: string;
};

function CopyButton({
  label,
  value,
  onCopied,
}: {
  label: string;
  value: string;
  onCopied: (id: string | null) => void;
}) {
  const { t } = useI18n();
  const [pending, setPending] = useState(false);

  return (
    <button
      type="button"
      className="settings-dev-copy"
      disabled={pending || !value.trim()}
      aria-label={`${t("settings.developerCopy")} ${label}`}
      onClick={() => {
        setPending(true);
        void copyText(value).then((ok) => {
          onCopied(ok ? label : null);
          setPending(false);
        });
      }}
    >
      {t("settings.developerCopy")}
    </button>
  );
}

export function DeveloperPanel(props: DeveloperPanelProps) {
  const { health } = props;
  const { t } = useI18n();
  const [copied, setCopied] = useState<string | null>(null);

  const items = useMemo((): DevItem[] => {
    return [
      {
        id: "trace",
        label: t("settings.developerTracePath"),
        value: health?.trace_path ?? "",
        hint: t("settings.developerTracePathHint"),
      },
      {
        id: "eval",
        label: t("settings.developerEval"),
        value: "uv run harnesslab eval",
        hint: t("settings.developerEvalHint"),
      },
      {
        id: "pricing",
        label: t("settings.developerPricing"),
        value: "uv run harnesslab pricing fingerprint",
        hint: t("settings.developerPricingHint"),
      },
      {
        id: "replay",
        label: t("settings.developerReplay"),
        value: health?.trace_path
          ? `uv run harnesslab replay ${JSON.stringify(health.trace_path)}`
          : "",
        hint: t("settings.developerReplayHint"),
      },
    ];
  }, [health?.trace_path, t]);

  const fingerprint = health?.pricing_fingerprint;

  return (
    <details className="settings-section settings-developer">
      <summary>{t("settings.developer")}</summary>
      <p className="settings-developer-hint">{t("settings.developerHint")}</p>

      {fingerprint ? (
        <div className="settings-dev-fingerprint">
          <span className="settings-dev-fingerprint-label">
            {t("settings.developerFingerprint")}
          </span>
          <code className="settings-dev-fingerprint-value" title={fingerprint}>
            {fingerprint}
          </code>
          <CopyButton label="fingerprint" value={fingerprint} onCopied={setCopied} />
        </div>
      ) : null}

      <ul className="settings-dev-list">
        {items.map((item) => (
          <li key={item.id} className="settings-dev-item">
            <div className="settings-dev-item-head">
              <span className="settings-dev-item-label">{item.label}</span>
              <CopyButton label={item.label} value={item.value} onCopied={setCopied} />
            </div>
            <code className="settings-dev-item-value">{item.value || "—"}</code>
            {item.hint ? <p className="settings-dev-item-hint">{item.hint}</p> : null}
          </li>
        ))}
      </ul>

      {copied ? (
        <p className="settings-dev-copied" aria-live="polite">
          {t("settings.developerCopied", { label: copied })}
        </p>
      ) : null}
    </details>
  );
}
