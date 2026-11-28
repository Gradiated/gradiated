const dateTime = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

const time = new Intl.DateTimeFormat("en-US", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export const formatDateTime = (iso: string) =>
  `${dateTime.format(new Date(iso))} UTC`;

export const formatTime = (iso: string) => time.format(new Date(iso));

export const formatCount = (value: number) => value.toLocaleString("en-US");

export const formatTokens = (value: number) => compact.format(value);

export const formatCost = (usd: number) =>
  usd > 0 && usd < 0.01
    ? "<$0.01"
    : usd.toLocaleString("en-US", { style: "currency", currency: "USD" });

export const formatBytes = (bytes: number) => {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;

  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }

  return `${unit === 0 ? value : value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
};

export const formatDuration = (seconds: number) => {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;

  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;

  return rest ? `${hours} h ${rest} min` : `${hours} h`;
};

export const shortId = (id: string) =>
  id.replace(/^([a-z]+_)?(.{8}).*$/, "$1$2");

export const formatScore = (value: number) => value.toFixed(3);
