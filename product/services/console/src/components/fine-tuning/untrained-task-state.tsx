import { ThresholdProgress } from "./threshold-progress";
import type { ReactNode } from "react";

export const UntrainedTaskState = ({
  title,
  icon,
  action,
}: {
  title: string;
  icon?: ReactNode;
  action?: ReactNode;
}) => (
  <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border bg-card px-6 text-center">
    {icon ? <span className="mb-3">{icon}</span> : null}
    <h3 className="font-medium">{title}</h3>
    {action ?? <ThresholdProgress label="First training" />}
  </div>
);
