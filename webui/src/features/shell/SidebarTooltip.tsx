import { useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";

type SidebarTooltipProps = {
  anchor: HTMLElement;
  label: string;
};

export function SidebarTooltip({ anchor, label }: SidebarTooltipProps) {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    const update = () => {
      const rect = anchor.getBoundingClientRect();
      const sidebar = document.getElementById("app-sidebar");
      const sidebarRight = sidebar?.getBoundingClientRect().right ?? rect.right;
      setPosition({
        top: rect.top + rect.height / 2,
        left: sidebarRight + 8,
      });
    };

    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [anchor]);

  if (!position) {
    return null;
  }

  return createPortal(
    <span
      className="app-sidebar-tooltip"
      style={{
        top: position.top,
        left: position.left,
      }}
    >
      {label}
    </span>,
    document.body
  );
}
