import { Ban, Check, ChevronDown, CircleAlert, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  STAGE_LABEL,
  STAGE_ORDER,
  TERMINAL_STAGES,
  describeEvent,
  runLogByStage,
  runProgress,
  runTimeline,
  type RunStage,
  type TrainingRunEvent,
  type TrainingRunRow,
} from "@/store/mock-fine-tuning";

const formatDuration = (ms: number) => {
  const s = Math.max(1, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min` : `${(m / 60).toFixed(1)} h`;
};
const clock = (iso: string) => iso.slice(11, 19);

/** The run's step list, derived entirely from `run.jsonl` (`TrainingRunEvent[]`). */
export const StageTimeline = ({
  run,
  events,
  onCancel,
}: {
  run: TrainingRunRow;
  events: TrainingRunEvent[];
  onCancel?: () => void;
}) => {
  const timeline = useMemo(() => runTimeline(events), [events]);
  const byStage = useMemo(() => runLogByStage(events), [events]);
  const progress = useMemo(() => runProgress(events), [events]);
  const isTerminal = TERMINAL_STAGES.includes(run.stage);
  const stopped =
    run.stage === "failed" ||
    run.stage === "cancelled" ||
    run.stage === "cancelling";
  const visited = timeline.map((t) => t.stage);

  // After a stop, the stages that never ran are listed as skipped (Vercel-style).
  const steps: RunStage[] = stopped
    ? [
        ...STAGE_ORDER.filter((s) => visited.includes(s) && s !== "succeeded"),
        run.stage,
        ...STAGE_ORDER.filter((s) => !visited.includes(s) && s !== "succeeded"),
      ]
    : STAGE_ORDER;

  const [openStage, setOpenStage] = useState<RunStage | null>(
    isTerminal ? (stopped ? run.stage : null) : run.stage,
  );
  useEffect(() => {
    setOpenStage(isTerminal ? (stopped ? run.stage : null) : run.stage);
  }, [run.id, run.stage, isTerminal, stopped]);

  const enteredAt = (stage: RunStage) =>
    timeline.find((t) => t.stage === stage)?.entered_at;
  const nextEnteredAt = (stage: RunStage) => {
    const i = timeline.findIndex((t) => t.stage === stage);
    return i >= 0 ? timeline[i + 1]?.entered_at : undefined;
  };

  return (
    <div>
      <ol className="divide-y rounded-lg border">
        {steps.map((stage, i) => {
          const entered = enteredAt(stage);
          const isCurrent = stage === run.stage && !isTerminal;
          const isBad =
            stage === run.stage &&
            (run.stage === "failed" || run.stage === "cancelled");
          const isDone = Boolean(entered) && !isCurrent && !isBad;
          const isPending = !entered;
          const isOpen = openStage === stage && !isPending;
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
                onClick={() => setOpenStage(isOpen ? null : stage)}
                className={`flex w-full items-center gap-3 px-3.5 py-2.5 text-left text-sm ${isPending ? "text-muted-foreground" : "hover:bg-muted/40"} ${
                  i === 0 ? "rounded-t-lg" : ""
                } ${i === steps.length - 1 && !isOpen ? "rounded-b-lg" : ""}`}
              >
                <ChevronDown
                  className={`size-3.5 shrink-0 text-muted-foreground transition-transform ${isOpen ? "" : "-rotate-90"} ${isPending ? "invisible" : ""}`}
                />
                <span className={`flex-1 ${isPending ? "" : "font-medium"}`}>
                  {STAGE_LABEL[stage]}
                </span>
                {stage === "training" && isCurrent && progress ? (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    step {progress.step}/{progress.total_steps} · reward{" "}
                    {progress.mean_reward.toFixed(2)}
                  </span>
                ) : null}
                <span className="w-16 text-right text-xs text-muted-foreground tabular-nums">
                  {showDuration
                    ? formatDuration(duration)
                    : isPending && stopped
                      ? "Skipped"
                      : ""}
                </span>
                <span
                  className={`grid size-5 shrink-0 place-items-center rounded-full ${
                    isBad
                      ? "bg-destructive text-white"
                      : isCurrent
                        ? "text-[#6e7f31]"
                        : isDone
                          ? "bg-[#6e7f31] text-white"
                          : "border border-border text-muted-foreground"
                  }`}
                >
                  {isBad ? (
                    stage === "failed" ? (
                      <CircleAlert className="size-3.5" />
                    ) : (
                      <Ban className="size-3.5" />
                    )
                  ) : isCurrent ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : isDone ? (
                    <Check className="size-3" />
                  ) : isPending && stopped ? (
                    <Ban className="size-3" />
                  ) : null}
                </span>
              </button>
              {isOpen && lines.length ? (
                <pre
                  className={`max-h-64 overflow-auto border-t bg-muted/50 px-4 py-3 font-mono text-[11px] leading-5 text-foreground ${i === steps.length - 1 ? "rounded-b-lg" : ""}`}
                >
                  {lines
                    .map((e, j) => {
                      const line = `${clock(e.at)} ${e.source === "trainer" ? "[trainer] " : ""}${describeEvent(e)}`;
                      const previous = lines[j - 1];
                      return previous && previous.attempt !== e.attempt
                        ? `\n── attempt ${e.attempt} ──\n${line}`
                        : line;
                    })
                    .join("\n")}
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
