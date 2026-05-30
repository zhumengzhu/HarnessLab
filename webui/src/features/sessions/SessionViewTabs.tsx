import { useI18n } from "../../lib/i18n";

export type SessionViewTab = "chat" | "trace" | "activity";

type SessionViewTabsProps = {
  value: SessionViewTab;
  onChange: (tab: SessionViewTab) => void;
  showTrace: boolean;
};

export function SessionViewTabs(props: SessionViewTabsProps) {
  const { value, onChange, showTrace } = props;
  const { t } = useI18n();

  return (
    <div className="session-view-tabs" role="tablist" aria-label={t("session.views")}>
      <button
        type="button"
        role="tab"
        aria-selected={value === "chat"}
        className={value === "chat" ? "active" : undefined}
        onClick={() => onChange("chat")}
      >
        {t("session.tabChat")}
      </button>
      {showTrace ? (
        <button
          type="button"
          role="tab"
          aria-selected={value === "trace"}
          className={value === "trace" ? "active" : undefined}
          onClick={() => onChange("trace")}
        >
          {t("session.tabTrace")}
        </button>
      ) : null}
      <button
        type="button"
        role="tab"
        aria-selected={value === "activity"}
        className={value === "activity" ? "active" : undefined}
        onClick={() => onChange("activity")}
      >
        {t("session.tabActivity")}
      </button>
    </div>
  );
}
