import { THEME_FAMILIES, type ThemeFamily } from "../shell/theme";
import { useI18n } from "../../lib/i18n";

type ThemeFamilyPickerProps = {
  value: ThemeFamily;
  onChange: (family: ThemeFamily) => void;
};

export function ThemeFamilyPicker({ value, onChange }: ThemeFamilyPickerProps) {
  const { t } = useI18n();

  return (
    <div className="theme-family-grid" role="radiogroup" aria-label={t("settings.themeFamily")}>
      {THEME_FAMILIES.map((family) => {
        const selected = value === family.id;
        return (
          <button
            key={family.id}
            type="button"
            role="radio"
            aria-checked={selected}
            className={`theme-family-card theme-family-card--${family.id}${selected ? " theme-family-card--selected" : ""}`}
            onClick={() => onChange(family.id)}
          >
            <span className="theme-family-card-icon" aria-hidden>
              {family.icon}
            </span>
            <span className="theme-family-card-label">{t(family.labelKey)}</span>
            <span className="theme-family-card-hint">{t(family.hintKey)}</span>
            {selected ? (
              <span className="theme-family-card-check" aria-hidden>
                ✓
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
