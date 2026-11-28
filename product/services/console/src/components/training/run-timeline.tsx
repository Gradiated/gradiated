import { useMemo, type ReactNode } from "react";

import { toneText } from "@/components/training/status-badge";
import { SectionCard } from "@/components/training/training-ui";
import { formatTime } from "@/lib/grad/format";
import { runTimeline } from "@/lib/grad/run-events";
import type { RunEvent } from "@/lib/grad/types";
import { cn } from "@/lib/utils";

const DOT = {
  neutral: "border-muted-foreground/50 bg-card",
  active: "border-[#7a9a1f] bg-[#7a9a1f]",
  success: "border-[#7a9a1f] bg-[#7a9a1f]",
  warning: "border-[#c48a12] bg-[#c48a12]",
  danger: "border-destructive bg-destructive",
} as const;

export const RunTimeline = ({
  events,
  live,
}: {
  events: readonly RunEvent[];
  live: ReactNode;
}) => {
  const entries = useMemo(() => runTimeline(events).reverse(), [events]);

  return (
    <SectionCard
      title="Timeline"
      description="Phases and attempts, newest first."
      actions={live}
      contentClassName="max-h-[440px] overflow-y-auto"
    >
      {entries.length ? (
        <ol className="relative space-y-4 border-l pl-5">
          {entries.map((entry) => (
            <li key={`${entry.seq}-${entry.title}`} className="relative">
              <span
                aria-hidden="true"
                className={cn(
                  "absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2",
                  DOT[entry.tone],
                )}
              />
              <div className="flex items-baseline justify-between gap-3">
                <p
                  className={cn(
                    "text-sm font-medium",
                    entry.tone !== "neutral" && toneText[entry.tone],
                  )}
                >
                  {entry.title}
                </p>
                <time
                  dateTime={entry.at}
                  className="shrink-0 font-mono text-xs text-muted-foreground"
                >
                  {formatTime(entry.at)}
                </time>
              </div>
              {entry.detail ? (
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {entry.detail}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted-foreground">No events yet.</p>
      )}
    </SectionCard>
  );
};
