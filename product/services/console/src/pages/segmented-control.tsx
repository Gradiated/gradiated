export const SegmentedControl = <Value extends string | number>({
  value,
  options,
  onChange,
}: {
  value: Value;
  options: readonly { value: Value; label: string }[];
  onChange: (value: Value) => void;
}) => (
  <div className="flex rounded-md bg-muted p-0.5">
    {options.map((option) => (
      <button
        key={option.value}
        type="button"
        aria-pressed={value === option.value}
        onClick={() => onChange(option.value)}
        className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${value === option.value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
      >
        {option.label}
      </button>
    ))}
  </div>
);
