/** Backend diagnostics contain stable codes and stack locations, never raw error
 * messages, request bodies, headers, query strings, or customer identities. */
export type ServiceLogFields = {
  request_id?: string;
  method?: string;
  route?: string;
  status?: number;
  duration_ms?: number;
  loop?: string;
  dependency?: string;
  attempt?: number;
  retry_ms?: number;
  signal?: string;
  error?: unknown;
};

const diagnosticCode = (error: unknown): string | undefined => {
  if (!error || typeof error !== "object" || !("code" in error)) return;
  const code = String(error.code);
  return /^(?:[A-Z0-9]{5}|E[A-Z_]{2,30}|[0-9]{1,5})$/.test(code)
    ? code
    : undefined;
};

export const createServiceLogger = (
  service: "api" | "worker",
  write: (line: string) => void = (line) => console.log(line),
  now: () => number = Date.now,
) => {
  let windowStart = now();
  let emitted = 0;
  let suppressed = 0;

  return (
    level: "info" | "warn" | "error",
    event: string,
    fields: ServiceLogFields = {},
  ): void => {
    const timestamp = now();
    if (timestamp - windowStart >= 1_000) {
      windowStart = timestamp;
      emitted = 0;
    }
    if (emitted >= 10) {
      suppressed += 1;
      return;
    }
    emitted += 1;

    const safe: Record<string, string | number | string[] | undefined> = {};
    for (const key of [
      "method",
      "route",
      "loop",
      "dependency",
      "signal",
    ] as const) {
      if (typeof fields[key] === "string")
        safe[key] = fields[key].slice(0, 256);
    }
    for (const key of [
      "status",
      "duration_ms",
      "attempt",
      "retry_ms",
    ] as const) {
      if (Number.isFinite(fields[key])) safe[key] = fields[key];
    }
    if (fields.request_id && /^[0-9a-f-]{36}$/i.test(fields.request_id)) {
      safe.request_id = fields.request_id;
    }
    if (fields.error !== undefined) {
      safe.error_type =
        fields.error instanceof Error
          ? fields.error.constructor.name
          : "UnknownError";
      safe.error_code = diagnosticCode(fields.error);
      if (fields.error instanceof Error) {
        safe.error_frames = fields.error.stack
          ?.split("\n")
          .filter((line) => /^\s+at /.test(line))
          .slice(0, 8);
      }
    }

    write(
      JSON.stringify({
        timestamp: new Date(timestamp).toISOString(),
        service,
        level,
        event,
        ...safe,
        suppressed_events: suppressed,
      }),
    );
    suppressed = 0;
  };
};
