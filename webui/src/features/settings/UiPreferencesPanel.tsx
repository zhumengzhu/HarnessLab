import type { ActivityDisplayMode, ChatTextSize } from "../chat/chatDisplay";
import type { ThemeFamily, ThemePreference } from "../shell/theme";
import type { Locale } from "../../lib/i18n";
import { useI18n } from "../../lib/i18n";
import { SegmentedControl } from "./SegmentedControl";
import { ThemeFamilyPicker } from "./ThemeFamilyPicker";

type UiPreferencesPanelProps = {
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

export function UiPreferencesPanel(props: UiPreferencesPanelProps) {
  const {
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

  return (
    <section className="settings-ui-prefs" aria-labelledby="ui-prefs-heading">
      <div className="settings-ui-prefs-intro">
        <h3 id="ui-prefs-heading">{t("settings.uiPrefs")}</h3>
        <p className="settings-ui-prefs-hint">{t("settings.uiPrefsHint")}</p>
      </div>

      <div className="settings-card-grid">
        <article className="settings-card">
          <header className="settings-card-header">
            <span className="settings-card-icon" aria-hidden>
              ✦
            </span>
            <div>
              <h4 className="settings-card-title">{t("settings.appearanceCard")}</h4>
              <p className="settings-card-subtitle">{t("settings.appearanceCardHint")}</p>
            </div>
          </header>

          <div className="settings-card-rows">
            <div className="settings-card-row settings-card-row-stack">
              <span className="settings-card-row-label">{t("settings.themeFamily")}</span>
              <ThemeFamilyPicker value={themeFamily} onChange={onThemeFamilyChange} />
            </div>

            <div className="settings-card-row">
              <span className="settings-card-row-label">{t("settings.colorScheme")}</span>
              <SegmentedControl
                ariaLabel={t("settings.colorScheme")}
                value={themePreference}
                options={[
                  { value: "system", label: t("settings.themeSystem") },
                  { value: "light", label: t("settings.themeLight") },
                  { value: "dark", label: t("settings.themeDark") },
                ]}
                onChange={onThemePreferenceChange}
              />
            </div>

            <div className="settings-card-row">
              <span className="settings-card-row-label">{t("settings.language")}</span>
              <SegmentedControl
                ariaLabel={t("settings.language")}
                value={locale}
                options={[
                  { value: "zh", label: t("settings.langZh") },
                  { value: "en", label: t("settings.langEn") },
                ]}
                onChange={onLocaleChange}
              />
            </div>
          </div>
        </article>

        <article className="settings-card">
          <header className="settings-card-header">
            <span className="settings-card-icon" aria-hidden>
              💬
            </span>
            <div>
              <h4 className="settings-card-title">{t("settings.chatCard")}</h4>
              <p className="settings-card-subtitle">{t("settings.chatCardHint")}</p>
            </div>
          </header>

          <div className="settings-card-rows">
            <div className="settings-card-row">
              <span className="settings-card-row-label">{t("settings.activityDisplay")}</span>
              <SegmentedControl
                ariaLabel={t("settings.activityDisplay")}
                value={activityDisplay}
                options={[
                  { value: "compact", label: t("settings.compact") },
                  { value: "detailed", label: t("settings.detailed") },
                ]}
                onChange={onActivityDisplayChange}
              />
            </div>

            <div className="settings-card-row">
              <span className="settings-card-row-label">{t("settings.chatTextSize")}</span>
              <SegmentedControl
                ariaLabel={t("settings.chatTextSize")}
                value={chatTextSize}
                options={[
                  { value: "sm", label: "S" },
                  { value: "md", label: "M" },
                  { value: "lg", label: "L" },
                ]}
                onChange={onChatTextSizeChange}
              />
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
