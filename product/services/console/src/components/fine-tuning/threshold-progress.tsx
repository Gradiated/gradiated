import type { ReactNode } from "react";

import { formatPercent } from "@/lib/format";
import { TRAINING_TRACE_THRESHOLD } from "@/store/fine-tuning-types";

export const ThresholdProgress = ({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: number;
  compact?: boolean;
}) => (
  <div className={compact ? "" : "mt-4 w-72 text-left"}>
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      <span>{label}</span>
      <span className="tabular-nums">
        {value} / {TRAINING_TRACE_THRESHOLD} traces
      </span>
    </div>
    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
      <span
        className="block h-full rounded-full bg-primary"
        style={{ width: formatPercent(value / TRAINING_TRACE_THRESHOLD) }}
      />
    </div>
  </div>
);

export const UntrainedTaskState = ({
  title,
  icon,
  usableTraces,
  action,
}: {
  title: string;
  icon?: ReactNode;
  usableTraces: number;
  action?: ReactNode;
}) => (
  <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border bg-card px-6 text-center">
    {icon ? <span className="mb-3">{icon}</span> : null}
    <h3 className="font-medium">{title}</h3>
    {action ?? (
      <ThresholdProgress label="First training" value={usableTraces} />
    )}
  </div>
);
