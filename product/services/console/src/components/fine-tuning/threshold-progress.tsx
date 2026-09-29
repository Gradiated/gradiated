export const ThresholdProgress = ({
  label,
  compact = false,
}: {
  label: string;
  compact?: boolean;
}) => (
  <div className={compact ? "" : "mt-4 w-72 text-left"}>
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      <span>{label}</span>
      <span className="tabular-nums">— / 500 traces</span>
    </div>
    <div className="mt-2 h-1.5 rounded-full bg-muted" />
  </div>
);
