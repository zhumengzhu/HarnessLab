import { useEffect, useRef, useState } from "react";
import type { ContextSnapshot } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import {
  buildContextModalModel,
  ContextModalPanel,
} from "./contextModalShared";
import { getContextUsageLevel } from "./contextUsageLevel";

type ContextUsagePillProps = {
  snapshot: ContextSnapshot | null | undefined;
};

/** Compact context meter; click opens Cursor-style breakdown popover. */
export function ContextUsagePill({ snapshot }: ContextUsagePillProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const model = buildContextModalModel(snapshot);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      const root = wrapRef.current;
      if (root && !root.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!model) {
    return (
      <span className="composer-context-pill composer-context-pill-empty" aria-hidden>
        –
      </span>
    );
  }

  const { pct, ratio } = model;
  const level = getContextUsageLevel(ratio);

  return (
    <div className="composer-context-wrap" ref={wrapRef}>
      <button
        type="button"
        className={`composer-context-pill composer-context-pill--${level}`}
        title={t("chat.contextRingAria", { pct })}
        aria-expanded={open}
        aria-label={t("chat.contextRingAria", { pct })}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="composer-context-meter" aria-hidden>
          <span className="composer-context-meter-fill" style={{ width: `${Math.min(pct, 100)}%` }} />
        </span>
        <span className="composer-context-pct">{pct}%</span>
      </button>
      {open ? <ContextModalPanel model={model} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}
