type SegmentedOption<T extends string> = {
  value: T;
  label: string;
};

type SegmentedControlProps<T extends string> = {
  value: T;
  options: SegmentedOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
  variant?: "neutral" | "accent";
};

export function SegmentedControl<T extends string>(props: SegmentedControlProps<T>) {
  const { value, options, onChange, ariaLabel, variant = "neutral" } = props;

  return (
    <div
      className={`hl-segmented hl-segmented-${variant}`}
      role="group"
      aria-label={ariaLabel}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            className={`hl-segmented-btn${active ? " hl-segmented-btn-active" : ""}`}
            aria-pressed={active}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
