import { useState, type ReactNode } from "react";

type TraceDetailAccordionProps = {
  label: string;
  defaultOpen?: boolean;
  summaryPreview?: string;
  children: ReactNode;
};

/** Jaeger ``AccordionAttributes`` header + expandable body. */
export function TraceDetailAccordion(props: TraceDetailAccordionProps) {
  const { label, defaultOpen = true, summaryPreview, children } = props;
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className={`trace-detail-accordion${open ? " is-open" : ""}`}>
      <button
        type="button"
        className="trace-detail-accordion-head"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="trace-detail-accordion-chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
        <span className="trace-detail-accordion-label">{label}</span>
        {!open && summaryPreview ? (
          <span className="trace-detail-accordion-preview">{summaryPreview}</span>
        ) : null}
      </button>
      {open ? <div className="trace-detail-accordion-body">{children}</div> : null}
    </section>
  );
}
