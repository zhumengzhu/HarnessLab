import type { SlashMenuItem } from "./useComposerSlashMenu";
import { useI18n } from "../../lib/i18n";

type ComposerSlashMenuProps = {
  open: boolean;
  items: SlashMenuItem[];
  activeIndex: number;
  onPick: (item: SlashMenuItem) => void;
};

export function ComposerSlashMenu(props: ComposerSlashMenuProps) {
  const { open, items, activeIndex, onPick } = props;
  const { t } = useI18n();
  if (!open) return null;

  return (
    <div className="composer-slash-menu" role="listbox" aria-label={t("chat.slashCommands")}>
      {items.map((item, idx) => (
        <button
          key={`${item.group}-${item.name}`}
          type="button"
          role="option"
          aria-selected={idx === activeIndex}
          className={`composer-slash-item${idx === activeIndex ? " composer-slash-item-active" : ""}`}
          onMouseDown={(e) => {
            e.preventDefault();
            onPick(item);
          }}
        >
          <span className="composer-slash-usage">{item.usage}</span>
          <span className="composer-slash-desc">{item.description}</span>
          {item.group === "skill" ? (
            <span className="composer-slash-tag">{t("composer.skillTag")}</span>
          ) : item.kind === "admin" ? (
            <span className="composer-slash-tag">{t("composer.adminTag")}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}
