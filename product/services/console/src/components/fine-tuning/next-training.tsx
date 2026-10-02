import { useEffect, useState } from "react";
import { nextTrainingTime } from "@gradiated/contracts/training-schedule";

export const NextTraining = ({ schedule }: { schedule: string | null }) => {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const next = nextTrainingTime(schedule, now);

  return (
    <div className="space-y-1 text-xs">
      <p className="text-muted-foreground">Next training run</p>
      {next ? (
        <time
          dateTime={next.toISOString()}
          title={`${schedule} (UTC)`}
          className="font-medium tabular-nums"
        >
          {next.toLocaleString(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </time>
      ) : (
        <p className="text-muted-foreground">
          {schedule ? "No upcoming scheduled run" : "Manual training"}
        </p>
      )}
      {!schedule ? (
        <p className="text-muted-foreground">
          Set a schedule in task settings to train automatically.
        </p>
      ) : null}
    </div>
  );
};
