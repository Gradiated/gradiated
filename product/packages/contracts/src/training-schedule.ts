import { CronDate, CronExpressionParser } from "cron-parser";

export const nextTrainingTime = (
  cron: string | null,
  now = new Date(),
): Date | null => {
  if (!cron) return null;

  try {
    const endDate = new Date(now);
    endDate.setUTCFullYear(endDate.getUTCFullYear() + 28);
    const expression = CronExpressionParser.parse(cron, {
      currentDate: now,
      endDate,
      tz: "UTC",
    });

    while (expression.hasNext()) {
      const next = expression.next().toDate();
      // Temporal requires both day fields to match; cron-parser uses Unix's OR.
      if (
        expression.fields.dayOfMonth.values.some(
          (day) => day === next.getUTCDate(),
        ) &&
        expression.fields.dayOfWeek.values.some(
          (day) => day === next.getUTCDay(),
        )
      )
        return next;

      expression.reset(
        new CronDate(
          new Date(
            Date.UTC(
              next.getUTCFullYear(),
              next.getUTCMonth(),
              next.getUTCDate() + 1,
            ) - 1,
          ),
          "UTC",
        ),
      );
    }
  } catch {
    return null;
  }

  return null;
};
