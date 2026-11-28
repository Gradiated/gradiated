import { Badge } from "@/components/ui/badge";
import {
  EVAL_STATUS,
  IMPORT_STATUS,
  RUN_STATUS,
  type Tone,
} from "@/lib/grad/labels";
import type { EvalStatus, RunStatus } from "@/lib/grad/types";
import { cn } from "@/lib/utils";

const DOT: Record<Tone, string> = {
  neutral: "bg-muted-foreground/50",
  active: "bg-[#7a9a1f] ring-2 ring-[#7a9a1f]/25",
  success: "bg-[#7a9a1f]",
  warning: "bg-[#c48a12]",
  danger: "bg-destructive",
};

export const StatusBadge = ({
  label,
  tone,
  className,
}: {
  label: string;
  tone: Tone;
  className?: string;
}) => (
  <Badge
    variant="outline"
    className={cn(
      "gap-1.5 bg-card font-normal",
      tone === "danger" && "border-destructive/30 text-destructive",
      className,
    )}
  >
    <span className={cn("size-1.5 rounded-full", DOT[tone])} />
    {label}
  </Badge>
);

export const RunStatusBadge = ({ status }: { status: RunStatus }) => (
  <StatusBadge {...RUN_STATUS[status]} />
);

export const EvalStatusBadge = ({ status }: { status: EvalStatus }) => (
  <StatusBadge {...EVAL_STATUS[status]} />
);

export const ImportStatusBadge = ({
  status,
}: {
  status: keyof typeof IMPORT_STATUS;
}) => <StatusBadge {...IMPORT_STATUS[status]} />;

export const toneText: Record<Tone, string> = {
  neutral: "text-muted-foreground",
  active: "text-[#5b6f19]",
  success: "text-[#5b6f19]",
  warning: "text-[#9a6a00]",
  danger: "text-destructive",
};
