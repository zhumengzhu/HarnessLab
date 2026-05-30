import { useEffect, useRef, useState } from "react";
import type { ContextSnapshot } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import {
  buildContextModalModel,
  ContextModalPanel,
  DonutRing,
} from "./contextModalShared";
import { contextUsageClass, getContextUsageLevel } from "./contextUsageLevel";

type ContextRingProps = {
  snapshot: ContextSnapshot | null | undefined;
  /** Inline in composer toolbar (default) vs legacy float overlay. */
  placement?: "inline" | "float";
};

/** Donut gauge; click opens Cursor-style context breakdown (composer only). */
export function ContextRing({ snapshot, placement = "inline" }: ContextRingProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const model = buildContextModalModel(snapshot);
  const wrapClass =
    placement === "float" ? "ctx-ring-wrap composer-context-float" : "ctx-ring-wrap ctx-ring-inline";

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
      <div className={wrapClass} aria-hidden>
        <button type="button" className="ctx-ring-btn ctx-ring-empty" disabled title={t("chat.noContextData")}>
          <svg width={44} height={44} viewBox="0 0 44 44" className="ctx-ring-svg">
            <circle cx={22} cy={22} r={17} fill="none" className="ctx-ring-track" strokeWidth={5} />
          </svg>
          <span className="ctx-ring-pct">–</span>
        </button>
      </div>
    );
  }

  const { limit, segments, ratio, pct } = model;
  const level = getContextUsageLevel(ratio);

  return (
    <div className={wrapClass} ref={wrapRef}>
      <button
        type="button"
        className="ctx-ring-btn"
        title={t("chat.contextRingTitle", { pct })}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={t("chat.contextRingAria", { pct })}
      >
        <DonutRing ratio={ratio} segments={segments} limit={limit} />
        <span className={contextUsageClass("ctx-ring-pct", level)}>{pct}%</span>
      </button>
      {open ? (
        <ContextModalPanel
          model={model}
          onClose={() => setOpen(false)}
          className="ctx-modal-float"
        />
      ) : null}
    </div>
  );
}
