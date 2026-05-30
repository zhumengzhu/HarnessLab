import { useRef, useState } from "react";
import { useI18n } from "../../lib/i18n";
import { SidebarTooltip } from "./SidebarTooltip";

type SidebarVersionProps = {
  version: string | null | undefined;
  healthOk: boolean;
  collapsed: boolean;
};

export function SidebarVersion({ version, healthOk, collapsed }: SidebarVersionProps) {
  const { t } = useI18n();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);
  const label = version ? `v${version}` : "v—";
  const title = version ? `HarnessLab ${label}` : "HarnessLab";

  return (
    <div
      ref={wrapRef}
      className={`app-sidebar-version${collapsed ? " app-sidebar-version-collapsed" : ""}`}
      title={title}
      onMouseEnter={collapsed ? () => setHovered(true) : undefined}
      onMouseLeave={collapsed ? () => setHovered(false) : undefined}
      onFocus={collapsed ? () => setHovered(true) : undefined}
      onBlur={collapsed ? () => setHovered(false) : undefined}
    >
      {!collapsed ? (
        <>
          <span className="app-sidebar-version-label">{t("nav.version")}</span>
          <span className="app-sidebar-version-text">{label}</span>
        </>
      ) : null}
      <span
        className={`app-sidebar-version-status${healthOk ? " ok" : " bad"}`}
        aria-label={healthOk ? t("nav.healthOk") : t("nav.healthBad")}
        title={healthOk ? t("nav.healthOk") : t("nav.healthBad")}
      />
      {collapsed && hovered && wrapRef.current ? (
        <SidebarTooltip anchor={wrapRef.current} label={label} />
      ) : null}
    </div>
  );
}
