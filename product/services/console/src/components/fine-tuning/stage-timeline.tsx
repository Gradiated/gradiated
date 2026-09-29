import {
  Ban,
  Check,
  ChevronDown,
  CircleAlert,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import {
  initiallyOpenStage,
  stepState,
  stepsFor,
  type StepState,
} from "@/components/fine-tuning/stage-steps";
import { Button } from "@/components/ui/button";
import { formatElapsed } from "@/lib/format";
import {
  describeEvent,
  runLogByStage,
  runProgress,
  runTimeline,
} from "@/store/fine-tuning-run-log";
import {
  STAGE_LABEL,
  isTerminalStage,
  type RunStage,
  type TrainingRunEvent,
  type TrainingRunRow,
} from "@/store/fine-tuning-types";

const STEP_STYLE: Record<
  StepState,
  { icon: LucideIcon | null; iconClassName: string; className: string }
> = {
  done: {
    icon: Check,
    iconClassName: "size-3",
    className: "bg-[#6e7f31] text-white",
  },
  current: {
    icon: Loader2,
    iconClassName: "size-4 animate-spin",
    className: "text-[#6e7f31]",
  },
  failed: {
    icon: CircleAlert,
    iconClassName: "size-3.5",
    className: "bg-destructive text-white",
  },
  cancelled: {
    icon: Ban,
    iconClassName: "size-3.5",
    className: "bg-destructive text-white",
  },
  skipped: {
    icon: Ban,
    iconClassName: "size-3",
    className: "border border-border text-muted-foreground",
  },
  pending: {
    icon: null,
    iconClassName: "",
    className: "border border-border text-muted-foreground",
  },
};

const clock = (iso: string) => iso.slice(11, 19);

const formatStageLog = (lines: TrainingRunEvent[]) =>
  lines
    .map((event, index) => {
      const line = `${clock(event.at)} [${event.source}] ${describeEvent(event)}`;
      const previous = lines[index - 1];

      return previous && previous.attempt !== event.attempt
        ? `\n── attempt ${event.attempt} ──\n${line}`
        : line;
    })
    .join("\n");

export const StageTimeline = ({
  run,
  events,
  onCancel,
}: {
  run: TrainingRunRow;
  events: readonly TrainingRunEvent[];
  onCancel?: () => void;
}) => {
  const timeline = useMemo(() => runTimeline(events), [events]);
  const byStage = useMemo(() => runLogByStage(events), [events]);
  const progress = useMemo(() => runProgress(events), [events]);
  const isTerminal = isTerminalStage(run.stage);
  const visited = timeline.map((entry) => entry.stage);
  const steps = stepsFor(run.stage, visited);

  const selectionScope = `${run.id}:${run.stage}`;
  const [selection, setSelection] = useState<{
    scope: string;
    stage: RunStage | null;
  } | null>(null);
  const openStage =
    selection?.scope === selectionScope
      ? selection.stage
      : initiallyOpenStage(run.stage);

  const enteredAt = (stage: RunStage) =>
    timeline.find((entry) => entry.stage === stage)?.entered_at;
  const nextEnteredAt = (stage: RunStage) => {
    const index = timeline.findIndex((entry) => entry.stage === stage);

    return index >= 0 ? timeline[index + 1]?.entered_at : undefined;
  };

  return (
    <div>
      <ol className="divide-y rounded-lg border">
        {steps.map((stage, i) => {
          const state = stepState(stage, run.stage, visited);
          const style = STEP_STYLE[state];
          const Icon = style.icon;
          const isCurrent = state === "current";
          const entered = enteredAt(stage);
          const isPending = !entered;
          const isOpen = openStage === stage && !isPending;
          const isLast = i === steps.length - 1;

          const nextAt = nextEnteredAt(stage);
          const end = isCurrent
            ? Date.now()
            : nextAt
              ? new Date(nextAt).getTime()
              : null;
          const duration =
            entered && end !== null ? end - new Date(entered).getTime() : null;
          const showDuration =
            duration !== null && stage !== "succeeded" && stage !== "queued";
          const lines = byStage[stage] ?? [];

          return (
            <li key={stage}>
              <button
                type="button"
                disabled={isPending}
                onClick={() =>
                  setSelection({
                    scope: selectionScope,
                    stage: isOpen ? null : stage,
                  })
                }
                className={`flex w-full items-center gap-3 px-3.5 py-2.5 text-left text-sm ${isPending ? "text-muted-foreground" : "hover:bg-muted/40"} ${
                  i === 0 ? "rounded-t-lg" : ""
                } ${isLast && !isOpen ? "rounded-b-lg" : ""}`}
              >
                <ChevronDown
                  className={`size-3.5 shrink-0 text-muted-foreground transition-transform ${isOpen ? "" : "-rotate-90"} ${isPending ? "invisible" : ""}`}
                />
                <span className={`flex-1 ${isPending ? "" : "font-medium"}`}>
                  {STAGE_LABEL[stage]}
                </span>
                {stage === "training" && isCurrent && progress ? (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    step {progress.step}
                    {progress.total_steps === undefined
                      ? ""
                      : `/${progress.total_steps}`}
                    {progress.train_loss === undefined
                      ? ""
                      : ` · loss ${progress.train_loss.toFixed(3)}`}
                  </span>
                ) : null}
                <span className="w-16 text-right text-xs text-muted-foreground tabular-nums">
                  {showDuration
                    ? formatElapsed(duration)
                    : state === "skipped"
                      ? "Skipped"
                      : ""}
                </span>
                <span
                  className={`grid size-5 shrink-0 place-items-center rounded-full ${style.className}`}
                >
                  {Icon ? <Icon className={style.iconClassName} /> : null}
                </span>
              </button>
              {isOpen && lines.length ? (
                <pre
                  className={`max-h-64 overflow-auto border-t bg-muted/50 px-4 py-3 font-mono text-[11px] leading-5 text-foreground ${isLast ? "rounded-b-lg" : ""}`}
                >
                  {formatStageLog(lines)}
                  {isCurrent ? "\n▌" : ""}
                </pre>
              ) : null}
            </li>
          );
        })}
      </ol>
      {!isTerminal && run.stage !== "cancelling" && onCancel ? (
        <Button variant="outline" size="sm" className="mt-3" onClick={onCancel}>
          Cancel run
        </Button>
      ) : null}
    </div>
  );
};
