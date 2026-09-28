import { z } from "zod";

const MAX_POINTS = 11_000;

const datetime = z.iso.datetime({ offset: true });

export const timeRange = {
  start: datetime,
  end: datetime,
  step_seconds: z.number().positive().optional(),
};

export const optionalTimeRange = {
  start: datetime.optional(),
  end: datetime.optional(),
};

export const toTimestamp = (value: string): string =>
  new Date(value).toISOString();

export const rangeParameters = ({
  start,
  end,
  step_seconds,
}: z.output<z.ZodObject<typeof timeRange>>) => {
  const startMilliseconds = Date.parse(start);
  const endMilliseconds = Date.parse(end);
  if (startMilliseconds >= endMilliseconds) throw new Error("empty_range");

  const seconds = (endMilliseconds - startMilliseconds) / 1_000;
  const step = step_seconds ?? Math.max(15, Math.ceil(seconds / 120));
  if (seconds / step > MAX_POINTS) throw new Error("too_many_points");

  return {
    start: toTimestamp(start),
    end: toTimestamp(end),
    step: String(step),
  };
};

export const optionalRangeParameters = ({
  start,
  end,
}: z.output<z.ZodObject<typeof optionalTimeRange>>) => {
  if (start && end && Date.parse(start) >= Date.parse(end)) {
    throw new Error("empty_range");
  }

  return {
    ...(start && { start: toTimestamp(start) }),
    ...(end && { end: toTimestamp(end) }),
  };
};
