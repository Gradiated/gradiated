import {
  isTerminalRun,
  PHASE_LABEL,
  INTERRUPTION_LABEL,
} from "@/lib/grad/labels";
import { formatCount, formatTime } from "@/lib/grad/format";
import { PHASE_STEPS, phaseStepIndex } from "@/lib/grad/run-events";
import type { Run } from "@/lib/grad/types";
import { cn } from "@/lib/utils";

const queueDetail = (run: Run) => {
  if (run.phase !== "queued" && run.phase !== "waiting_for_compute")
    return null;
  // grad words why the run waits ("Queued behind 3 runs", GPU size, limits).
  if (run.queueMessage) return run.queueMessage;
  if (run.autoscaling) return "A worker is starting.";
  if (run.workersOnline) {
    return `${run.workersOnline} worker${run.workersOnline === 1 ? " is" : "s are"} busy; this run starts when one is free.`;
  }

  return "Waiting for a worker to pick up this run.";
};

export const RunProgress = ({ run }: { run: Run }) => {
  const terminal = isTerminalRun(run.status);
  const current =
    run.status === "completed" ? PHASE_STEPS.length : phaseStepIndex(run.phase);
  const percent = run.totalSteps
    ? Math.min(100, (run.currentStep / run.totalSteps) * 100)
    : 0;
  const interruption = run.lastInterruption;
  const waiting = queueDetail(run);

  return (
    <section
      aria-label="Run progress"
      className="rounded-xl border bg-card p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold">
          {run.status === "completed"
            ? "Completed"
            : run.phase
              ? PHASE_LABEL[run.phase]
              : "Queued"}
          {run.phaseSince && !terminal ? (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              since {formatTime(run.phaseSince)} UTC
            </span>
          ) : null}
        </h2>
        <p className="text-sm text-muted-foreground tabular-nums">
          Step{" "}
          <span className="font-medium text-foreground">
            {formatCount(run.currentStep)}
          </span>{" "}
          / {formatCount(run.totalSteps)}
          <span className="mx-2">·</span>
          Attempt{" "}
          <span className="font-medium text-foreground">
            {run.attempt}
          </span> / {run.maxAttempts}
        </p>
      </div>

      <ol className="mt-4 grid grid-cols-5 gap-1.5" aria-label="Phases">
        {[...PHASE_STEPS, { key: "done", label: "Done" }].map((step, index) => {
          const done = index < current || run.status === "completed";
          const active = index === current && !terminal;
          const failed =
            index === current && terminal && run.status !== "completed";

          return (
            <li key={step.key} aria-current={active ? "step" : undefined}>
              <span
                className={cn(
                  "block h-1.5 rounded-full bg-muted",
                  done && "bg-foreground/70",
                  active && "bg-[#7a9a1f]",
                  failed && "bg-destructive/70",
                )}
              />
              <span
                className={cn(
                  "mt-1.5 block truncate text-xs text-muted-foreground",
                  (active || failed) && "font-medium text-foreground",
                )}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>

      <div
        className="mt-4 h-1 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label="Training steps"
        aria-valuemin={0}
        aria-valuemax={run.totalSteps}
        aria-valuenow={run.currentStep}
      >
        <span
          className="block h-full rounded-full bg-foreground/80 transition-[width]"
          style={{ width: `${percent}%` }}
        />
      </div>

      {waiting && !terminal ? (
        <p className="mt-3 text-sm text-muted-foreground">{waiting}</p>
      ) : null}
      {interruption && !terminal ? (
        <p className="mt-3 text-sm text-muted-foreground">
          {INTERRUPTION_LABEL[interruption.reason]} at step{" "}
          {formatCount(interruption.step)} during attempt {interruption.attempt}
          {interruption.resumeStep === null
            ? "; restarted from the beginning."
            : `; resumed from step ${formatCount(interruption.resumeStep)}.`}
        </p>
      ) : null}
      {run.error ? (
        <p className="mt-3 text-sm text-destructive">{run.error}</p>
      ) : null}
    </section>
  );
};
