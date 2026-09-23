const utcDay = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

const compact = new Intl.NumberFormat(undefined, {
  notation: "compact",
  maximumFractionDigits: 2,
});

export const utcDayLabel = (date: string) =>
  utcDay.format(new Date(`${date}T00:00:00Z`));

export const compactNumber = (value: number | string) =>
  compact.format(Number(value));
