import type { Option } from "@/components/option-select";
import { cn } from "@/lib/utils";

// A compact single-choice switcher for two to four short options.
export const SegmentedControl = <Value extends string>({
  value,
  options,
  onValueChange,
  label,
  labelledBy,
  className,
}: {
  value: Value;
  options: readonly Option<Value>[];
  onValueChange: (value: Value) => void;
  label?: string;
  labelledBy?: string;
  className?: string;
}) => (
  <div
    role="radiogroup"
    aria-label={label}
    aria-labelledby={labelledBy}
    className={cn(
      "inline-grid auto-cols-fr grid-flow-col gap-0.5 rounded-lg bg-muted p-0.5",
      className,
    )}
  >
    {options.map((option) => {
      const selected = option.value === value;

      return (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={selected}
          disabled={option.disabled ?? false}
          className={cn(
            "rounded-md px-3 py-1 text-sm whitespace-nowrap transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
            selected
              ? "bg-background font-medium text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
          onClick={() => onValueChange(option.value)}
        >
          {option.label}
        </button>
      );
    })}
  </div>
);
